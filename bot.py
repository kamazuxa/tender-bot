import logging
logging.basicConfig(level=logging.INFO)
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters
)
from config import TELEGRAM_TOKEN, LOG_LEVEL, LOG_FILE, SERPAPI_KEY, OPENAI_API_KEY, OPENAI_MODEL
from damia import damia_client, extract_tender_number
from downloader import downloader
from analyzer import analyzer
import os
import re
import zipfile
import tempfile
from serpapi import GoogleSearch
import json
import openai
from urllib.parse import urlparse
import mimetypes
try:
    import httpx
except ImportError:
    httpx = None
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

EXCLUDE_DOMAINS = [
    "avito.ru", "wildberries.ru", "ozon.ru", "market.yandex.ru", "lavka.yandex.ru",
    "beru.ru", "goods.ru", "tmall.ru", "aliexpress.ru",
    "youtube.com", "youtu.be", "rutube.ru",
    "consultant.ru"
]
EXCLUDE_PATTERNS = ["gost", "wiki", "gos", ".edu", ".gov"]
EXCLUDE_MINUS_WORDS = ["гост", "википедия", "техусловия", "норматив", "техзадание"]
EXCLUDE_HTML = [
    'tender', 'zakupka', 'zakupki', 'тендер', 'закупка', 'видео',
    *EXCLUDE_MINUS_WORDS
]

def is_good_domain(url):
    netloc = urlparse(url).netloc.lower()
    return not any(domain in netloc for domain in EXCLUDE_DOMAINS)

async def fetch_html(url):
    if not httpx or not BeautifulSoup:
        return None
    # PDF-фильтр по расширению
    if url.lower().endswith('.pdf'):
        return None
    # PDF-фильтр по mime-type
    mime, _ = mimetypes.guess_type(url)
    if mime and 'pdf' in mime:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code == 200 and 'pdf' not in resp.headers.get('content-type', ''):
                soup = BeautifulSoup(resp.text, 'html.parser')
                # Вырезаем мусорные блоки
                for tag in soup(['header', 'footer', 'nav', 'aside']):
                    tag.decompose()
                # Оставляем только main, article, div.content если есть
                main = soup.find('main')
                article = soup.find('article')
                content_div = soup.find('div', class_='content')
                if main:
                    text = main.get_text(separator=' ', strip=True)
                elif article:
                    text = article.get_text(separator=' ', strip=True)
                elif content_div:
                    text = content_div.get_text(separator=' ', strip=True)
                else:
                    text = soup.get_text(separator=' ', strip=True)
                return text[:8000]  # Ограничим для GPT
    except Exception as e:
        logger.error(f"[bot] Ошибка скачивания {url}: {e}")
    return None

def format_price(price_raw):
    """Форматирует цену с пробелами и заменяет валюту на 'рублей'"""
    if isinstance(price_raw, str):
        # Если строка, пробуем отделить число и валюту
        parts = price_raw.split()
        if parts and parts[0].replace('.', '', 1).isdigit():
            num = float(parts[0]) if '.' in parts[0] else int(parts[0])
            formatted = f"{num:,}".replace(",", " ")
            return f"{formatted} рублей"
        else:
            # Если не удалось, возвращаем как есть
            return price_raw
    elif isinstance(price_raw, (int, float)):
        return f"{price_raw:,}".replace(",", " ") + " рублей"
    return str(price_raw)

def format_date(date_str):
    """Преобразует дату из формата YYYY-MM-DD в DD.MM.YYYY"""
    try:
        parts = date_str.split('-')
        if len(parts) == 3:
            return f"{parts[2]}.{parts[1]}.{parts[0]}"
        return date_str
    except Exception:
        return date_str

def format_phone(phone_raw):
    """Форматирует телефон в вид +74959941031"""
    digits = re.sub(r'\D', '', str(phone_raw))
    if digits.startswith('7') and len(digits) == 11:
        return f'+{digits}'
    return phone_raw

class TenderBot:
    def __init__(self):
        self.app = None
        self.user_sessions = {}  # Для хранения состояния пользователей
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start"""
        user = update.effective_user
        welcome_message = f"""
🤖 **Добро пожаловать в TenderBot!**

Привет, {user.first_name}! Я помогу вам анализировать тендеры в госзакупках.

**Как использовать:**
1. Отправьте номер тендера (19 цифр)
2. Или отправьте ссылку на тендер с сайта госзакупок
3. Я автоматически получу данные и проанализирую документы

**Команды:**
/start - это сообщение
/help - справка
/status - статус бота
/cleanup - очистка старых файлов

**Примеры:**
```
0123456789012345678
https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0123456789012345678
```

Начните с отправки номера или ссылки на тендер!
        """
        
        keyboard = [
            [InlineKeyboardButton("📋 Справка", callback_data="help")],
            [InlineKeyboardButton("🔧 Статус", callback_data="status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)
        logger.info(f"[bot] Пользователь {user.id} запустил бота")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help"""
        help_text = """
📋 **Справка по использованию TenderBot**

**Основные функции:**
• Автоматическое получение данных о тендерах
• Скачивание документов тендера (техзадание, условия и т.д.)
• ИИ-анализ документов с помощью OpenAI GPT
• Структурированный отчет с рекомендациями

**Поддерживаемые форматы:**
• 19-значный номер тендера
• 20-значный номер тендера  
• Ссылки на zakupki.gov.ru

**Что анализируется:**
• Краткое резюме тендера
• Товарные позиции
• Требования к упаковке и качеству
• Ключевые условия участия
• Рекомендации по участию
• Оценка сложности

**Ограничения:**
• Максимальный размер файла: 50MB
• Поддерживаемые форматы: PDF, DOC, DOCX, XLS, XLSX, TXT
• Анализ только текстовых документов

**Поддержка:**
При возникновении проблем обращайтесь к администратору.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /status"""
        status_text = f"""
🔧 **Статус TenderBot**

**Время работы:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Версия:** 2.0.0
**Статус:** ✅ Работает

**API статус:**
• DaMIA API: ✅ Доступен
• OpenAI API: ✅ Доступен

**Статистика:**
• Обработано тендеров: {len(self.user_sessions)}
• Скачано файлов: {len(list(downloader.download_dir.glob('*')))}

**Система:**
• Логирование: ✅ Активно
• VPN для OpenAI: ✅ Настроен
• Очистка файлов: ✅ Автоматическая
        """
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    async def cleanup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /cleanup"""
        try:
            deleted_count = downloader.cleanup_old_files()
            await update.message.reply_text(f"🧹 Очистка завершена! Удалено файлов: {deleted_count}")
        except Exception as e:
            logger.error(f"[bot] Ошибка очистки: {e}")
            await update.message.reply_text("❌ Ошибка при очистке файлов")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик текстовых сообщений"""
        user = update.effective_user
        message = update.message.text.strip()
        
        logger.info(f"[bot] Получено сообщение от {user.id}: {message[:50]}...")
        
        # Отправляем статус "печатает"
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        try:
            # Извлекаем номер тендера
            reg_number = extract_tender_number(message)
            
            if not reg_number:
                await update.message.reply_text(
                    "❗ Пожалуйста, укажите корректный регистрационный номер закупки (19-20 цифр) или ссылку на тендер.\n\n"
                    "Примеры:\n"
                    "• 0123456789012345678\n"
                    "• https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0123456789012345678"
                )
                return
            
            # Сохраняем сессию пользователя
            self.user_sessions[user.id] = {
                'reg_number': reg_number,
                'timestamp': datetime.now(),
                'status': 'processing'
            }
            
            await update.message.reply_text(f"🔍 Ищу тендер {reg_number}...")
            
            # Получаем данные о тендере
            tender_data = await damia_client.get_tender_info(reg_number)
            logger.info(f"Ответ DaMIA: {tender_data}")
            
            if not tender_data:
                await update.message.reply_text(
                    f"❌ Не удалось найти тендер с номером {reg_number}.\n"
                    "Проверьте правильность номера или попробуйте позже."
                )
                return
            
            # Форматируем информацию о тендере
            formatted_info = damia_client.format_tender_info(tender_data)
            
            # Сохраняем данные тендера в сессии для последующего анализа
            self.user_sessions[user.id]['tender_data'] = tender_data
            self.user_sessions[user.id]['formatted_info'] = formatted_info
            
            # Отправляем основную информацию с кнопками
            await self._send_tender_info(update, formatted_info, reg_number)
            
            # Обновляем статус сессии
            self.user_sessions[user.id]['status'] = 'ready_for_analysis'
            
        except Exception as e:
            logger.error(f"[bot] Ошибка обработки сообщения: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке запроса.\n"
                "Попробуйте позже или обратитесь к администратору."
            )
    
    async def _send_tender_info(self, update: Update, tender_info: dict, reg_number: str) -> None:
        """Отправляет основную информацию о закупке с кнопками для дополнительных данных"""
        info_text = f"""
📋 **Информация о закупке**

📊 **Статус:** {tender_info['status']}
📋 **Федеральный закон:** {tender_info['federal_law']}-ФЗ
🏢 **Заказчик:** {tender_info['customer']}
📝 **ИНН:** {tender_info['customer_inn']}
📍 **Адрес:** {tender_info['customer_address']}
📄 **Предмет поставки:** {tender_info['subject']}
💰 **Цена:** {format_price(tender_info['price'])}
📅 **Дата публикации:** {format_date(tender_info['publication_date'])}
⏰ **Срок подачи до:** {format_date(tender_info['submission_deadline'])}

📍 **Место поставки:** {tender_info['delivery_place']}"""
        keyboard = [
            [InlineKeyboardButton("📦 Товарные позиции", callback_data=f"products_{reg_number}")],
            [InlineKeyboardButton("📄 Документы", callback_data=f"documents_{reg_number}")],
            [InlineKeyboardButton("🏢 Подробная информация", callback_data=f"details_{reg_number}")],
            [InlineKeyboardButton("📊 Подробный анализ", callback_data=f"analyze_{reg_number}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(info_text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _analyze_documents(self, tender_data, files):
        # Новый экспертный промпт для анализа и генерации поисковых запросов
        prompt = (
            "Ты — эксперт по госзакупкам и анализу товарных позиций для поиска поставщиков.\n"
            "Вот текст закупочной документации и технического задания (ТЗ). Проанализируй его комплексно и выполни следующие задачи:\n"
            "\nДай краткое описание закупки: какие товары требуются, в каком объёме, какие есть особенности (ГОСТ, фасовка, сорт, единицы измерения, сроки и т.п.).\n"
            "\nОпредели потенциальные риски и подводные камни для участника закупки:\n"
            "– есть ли неясности в ТЗ?\n"
            "– указана ли конкретная упаковка или требования, которые сложно соблюсти?\n"
            "– есть ли ограничения по поставке, логистике, сертификации и т.д.?\n"
            "\nДай рекомендации: стоит ли участвовать в закупке с учётом этих рисков? Почему да или почему нет?\n"
            "\nСформируй поисковые запросы в Яндексе для каждой товарной позиции, чтобы найти поставщиков в России. Запросы должны быть максимально релевантными для нахождения коммерческих предложений, цен и контактов. Включай: – наименование товара (кратко), – сорт/марку/модель, – ГОСТ/ТУ, – фасовку/упаковку, – объём (если применимо), – ключевые слова: купить, оптом, цена, поставщик.\n"
            "\nДай результат в виде:\n"
            "Анализ: <summary>\n"
            "Поисковые запросы:\n"
            "1. <позиция>: <поисковый запрос>\n2. ...\n"
        )
        # ... существующий код анализа ...
        # Вызов GPT с этим промптом и files
        # ...
        # После получения ответа парсим summary и поисковые запросы
        # Возвращаем analysis_result с полями 'overall_analysis', 'search_queries', 'raw_data'
        print("[bot] Перед вызовом анализа тендера")
        print(f"[bot] Документы для анализа: {files if 'files' in locals() else 'нет переменной files'}")
        analysis_result = await analyzer.analyze_tender_documents(tender_data, files)
        print("[bot] После вызова анализа тендера")
        return analysis_result
    
    async def _send_analysis_to_chat(self, bot, chat_id: int, analysis_result: dict) -> None:
        if not analysis_result:
            logger.error(f"[bot] analysis_result is None! Не удалось проанализировать тендер. analysis_result: {analysis_result}")
            await bot.send_message(chat_id=chat_id, text="❌ Не удалось проанализировать тендер. Попробуйте позже.")
            return
        if not isinstance(analysis_result, dict):
            logger.error(f"[bot] analysis_result не dict: {analysis_result}")
            await bot.send_message(chat_id=chat_id, text="❌ Не удалось проанализировать тендер (неверный формат данных). Попробуйте позже.")
            return
        overall = analysis_result.get('overall_analysis', {})
        summary = overall.get('summary', 'Анализ недоступен')
        
        # Разбиваем длинный анализ на части
        if len(summary) > 4000:
            parts = [summary[i:i+4000] for i in range(0, len(summary), 4000)]
            for i, part in enumerate(parts):
                if i == 0:
                    await bot.send_message(chat_id=chat_id, text=f"🤖 **Анализ тендера** (часть {i+1}/{len(parts)}):\n\n{part}", parse_mode='Markdown')
                else:
                    await bot.send_message(chat_id=chat_id, text=f"🤖 **Продолжение анализа** (часть {i+1}/{len(parts)}):\n\n{part}", parse_mode='Markdown')
        else:
            await bot.send_message(chat_id=chat_id, text=f"🤖 **Анализ тендера:**\n\n{summary}", parse_mode='Markdown')
        
        # Сохраняем поисковые запросы в сессию пользователя
        search_queries = analysis_result.get('search_queries', {})
        for user_id, session in self.user_sessions.items():
            if session.get('status') in ['ready_for_analysis', 'completed']:
                session['search_queries'] = search_queries
        # Сохраняем список позиций (для кнопок)
        tender_data = analysis_result.get('raw_data') or overall.get('raw_data')
        product_info = tender_data.get('Продукт', {})
        print(f"[bot] tender_data['Продукт']: {product_info}")
        objects = product_info.get('ОбъектыЗак', [])
        print(f"[bot] product_info['ОбъектыЗак']: {objects}")
        for user_id, session in self.user_sessions.items():
            if session.get('status') in ['ready_for_analysis', 'completed']:
                session['objects'] = objects
        # После анализа добавляем кнопку поиска поставщиков
        keyboard = [[InlineKeyboardButton("🔎 Найти поставщиков", callback_data="find_suppliers")]]
        await bot.send_message(chat_id=chat_id, text="Хотите найти поставщиков по результатам анализа?", reply_markup=InlineKeyboardMarkup(keyboard))
    
    async def _send_analysis(self, update: Update, analysis_result: dict) -> None:
        """Отправляет результаты анализа"""
        if not analysis_result:
            logger.error(f"[bot] analysis_result is None! Не удалось проанализировать тендер. analysis_result: {analysis_result}")
            await update.message.reply_text("❌ Не удалось проанализировать тендер. Попробуйте позже.")
            return
        if not isinstance(analysis_result, dict):
            logger.error(f"[bot] analysis_result не dict: {analysis_result}")
            await update.message.reply_text("❌ Не удалось проанализировать тендер (неверный формат данных). Попробуйте позже.")
            return
        overall = analysis_result.get('overall_analysis', {})
        summary = overall.get('summary', 'Анализ недоступен')
        
        # Разбиваем длинный анализ на части
        if len(summary) > 4000:
            parts = [summary[i:i+4000] for i in range(0, len(summary), 4000)]
            for i, part in enumerate(parts):
                if i == 0:
                    await update.message.reply_text(f"🤖 **Анализ тендера** (часть {i+1}/{len(parts)}):\n\n{part}", parse_mode='Markdown')
                else:
                    await update.message.reply_text(f"🤖 **Продолжение анализа** (часть {i+1}/{len(parts)}):\n\n{part}", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"🤖 **Анализ тендера:**\n\n{summary}", parse_mode='Markdown')
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик callback запросов"""
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id  # Теперь user_id всегда определён
        
        if query.data == "help":
            await self.help_command(update, context)
        elif query.data == "status":
            await self.status_command(update, context)
        elif query.data == "cleanup":
            await self.cleanup_command(update, context)
        elif query.data.startswith("products_") and not query.data.startswith("products_page_"):
            reg_number = query.data.split("_")[1]
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            tender_data = self.user_sessions[user_id]['tender_data']
            # Первая страница: отправляем новое сообщение
            sent = await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Загрузка товарных позиций..."
            )
            await self._send_products_list_to_chat(context.bot, query.message.chat_id, tender_data, page=0, message_id=sent.message_id)
        elif query.data.startswith("products_page_"):
            try:
                page = int(query.data.split("_")[2])
            except Exception:
                page = 0
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            tender_data = self.user_sessions[user_id]['tender_data']
            # Навигация: обновляем текущее сообщение
            logger.info(f"[bot] Навигация по товарам: page={page}, message_id={query.message.message_id}")
            await self._send_products_list_to_chat(context.bot, query.message.chat_id, tender_data, page=page, message_id=query.message.message_id)
        elif query.data == "current_page":
            await query.answer("Текущая страница")
            
        elif query.data.startswith("documents_"):
            reg_number = query.data.split("_")[1]
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            
            # Получаем данные из сессии
            tender_data = self.user_sessions[user_id]['tender_data']
            
            # Отправляем список документов с кнопками скачивания
            await self._send_documents_list_with_download(context.bot, query.message.chat_id, tender_data, reg_number, page=0)
            
        elif query.data.startswith("details_"):
            reg_number = query.data.split("_")[1]
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            
            # Получаем данные из сессии
            formatted_info = self.user_sessions[user_id]['formatted_info']
            
            # Отправляем подробную информацию
            await self._send_detailed_info_to_chat(context.bot, query.message.chat_id, formatted_info)
            
        elif query.data.startswith("download_"):
            reg_number = query.data.split("_")[1]
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            
            # Получаем данные из сессии
            tender_data = self.user_sessions[user_id]['tender_data']
            
            try:
                # Обновляем статус кнопки
                await query.edit_message_reply_markup(reply_markup=None)
                
                # Скачиваем документы
                await context.bot.send_message(chat_id=query.message.chat_id, text="📥 Скачиваю документы...")
                download_result = await downloader.download_documents(tender_data, reg_number)
                
                if download_result['success'] > 0 and download_result['files']:
                    logger.info(f"[bot] Содержимое download_result['files']: {download_result['files']}")
                    # Создаем временный архив
                    with tempfile.TemporaryDirectory() as tmpdir:
                        zip_path = os.path.join(tmpdir, f"tender_{reg_number}.zip")
                        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            for file_info in download_result['files']:
                                file_path = file_info['path']
                                arcname = os.path.basename(file_path)
                                zipf.write(file_path, arcname=arcname)
                        # Отправляем архив пользователю
                        with open(zip_path, 'rb') as zipfile_obj:
                            await context.bot.send_document(
                                chat_id=query.message.chat_id,
                                document=zipfile_obj,
                                filename=f"tender_{reg_number}.zip",
                                caption=f"Все документы по тендеру {reg_number}"
                            )
                    await context.bot.send_message(chat_id=query.message.chat_id, text="✅ Все документы отправлены архивом.")
                else:
                    await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Не удалось скачать документы")
                
            except Exception as e:
                logger.error(f"[bot] Ошибка скачивания документов тендера {reg_number}: {e}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Произошла ошибка при скачивании документов. Попробуйте позже."
                )
            
        elif query.data.startswith("analyze_"):
            reg_number = query.data.split("_")[1]
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            
            # Получаем данные из сессии
            tender_data = self.user_sessions[user_id]['tender_data']
            formatted_info = self.user_sessions[user_id]['formatted_info']
            
            try:
                # Обновляем статус кнопки
                await query.edit_message_reply_markup(reply_markup=None)
                
                # Скачиваем документы
                await context.bot.send_message(chat_id=query.message.chat_id, text="📥 Скачиваю документы...")
                download_result = await downloader.download_documents(tender_data, reg_number)
                
                if download_result['success'] > 0:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"✅ Скачано документов: {download_result['success']}\n❌ Не удалось скачать: {download_result['failed']}"
                    )
                    
                    # Анализируем документы
                    if download_result['files']:
                        await context.bot.send_message(chat_id=query.message.chat_id, text="🤖 Анализирую документы с помощью ИИ...")
                        analysis_result = await self._analyze_documents(formatted_info, download_result['files'])
                        if not analysis_result:
                            # Ошибка уже обработана и сообщение отправлено
                            return
                        # Отправляем анализ
                        await self._send_analysis_to_chat(context.bot, query.message.chat_id, analysis_result)
                    else:
                        await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Документы не найдены для анализа")
                else:
                    await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Не удалось скачать документы для анализа")
                
                # Обновляем статус сессии
                self.user_sessions[user_id]['status'] = 'ready_for_analysis'
                
            except Exception as e:
                logger.error(f"[bot] Ошибка анализа тендера {reg_number}: {e}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Произошла ошибка при анализе тендера. Попробуйте позже."
                )
        
        elif query.data.startswith("docs_page_"):
            parts = query.data.split("_")
            reg_number = parts[2]
            page = int(parts[3])
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            
            # Получаем данные из сессии
            tender_data = self.user_sessions[user_id]['tender_data']
            
            # Обновляем сообщение с новой страницей документов
            await self._update_documents_message(context.bot, query.message.chat_id, query.message.message_id, tender_data, reg_number, page)
        elif query.data == "find_suppliers":
            # После анализа: выводим кнопки по всем товарным позициям
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] not in ['ready_for_analysis', 'completed']:
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            objects = self.user_sessions[user_id].get('objects', [])
            if not objects:
                await query.edit_message_text("В этом тендере отсутствуют товарные позиции. Возможно, это закупка услуг или данные не заполнены.")
                return
            # Показываем кнопки с позициями
            keyboard = []
            for idx, obj in enumerate(objects):
                name = obj.get('Наименование', f'Позиция {idx+1}')
                keyboard.append([InlineKeyboardButton(name, callback_data=f"find_supplier_{idx}")])
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Выберите товарную позицию для поиска поставщика:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif query.data.startswith("find_supplier_"):
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] not in ['ready_for_analysis', 'completed']:
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            idx = int(query.data.split('_')[-1])
            objects = self.user_sessions[user_id].get('objects', [])
            if idx >= len(objects):
                await query.edit_message_text("❌ Позиция не найдена.")
                return
            obj = objects[idx]
            name = obj.get('Наименование', '')
            # Берём поисковый запрос, сгенерированный ИИ для этой позиции при анализе
            search_queries = self.user_sessions[user_id].get('search_queries', {})
            search_query = search_queries.get(idx, name)
            logger.info(f"[bot] Поисковый запрос для SerpAPI по позиции '{name}': {search_query}")
            await query.edit_message_text(f"🔎 Ищу поставщиков по позиции: {name} (по запросу: {search_query})...")
            search_results = await self._search_suppliers_serpapi(search_query)
            gpt_result = await self._extract_suppliers_gpt_ranked(search_query, search_results)
            await context.bot.send_message(chat_id=query.message.chat_id, text=gpt_result, parse_mode='HTML')
    
    async def _search_suppliers_serpapi(self, query):
        from concurrent.futures import ThreadPoolExecutor
        import asyncio
        loop = asyncio.get_event_loop()
        def search(lang):
            params = {
                "engine": "yandex",
                "text": query,
                "lang": lang,
                "api_key": SERPAPI_KEY,
                "num": 10
            }
            search = GoogleSearch(params)
            return search.get_dict()
        with ThreadPoolExecutor() as executor:
            ru = await loop.run_in_executor(executor, search, 'ru')
            en = await loop.run_in_executor(executor, search, 'en')
        return {'ru': ru, 'en': en}

    async def _extract_suppliers_gpt_ranked(self, search_query, search_results):
        if not httpx or not BeautifulSoup:
            return ("Для поиска поставщиков необходимо установить зависимости: httpx и beautifulsoup4.\n"
                    "Выполните команду: pip install httpx beautifulsoup4")
        links = []
        for lang in ['ru', 'en']:
            for item in search_results[lang].get('organic_results', []):
                url = item.get('link') or item.get('url')
                if not url:
                    continue
                netloc = urlparse(url).netloc.lower()
                # Фильтрация по домену и паттернам
                if any(domain in netloc for domain in EXCLUDE_DOMAINS):
                    continue
                if any(pat in url.lower() for pat in EXCLUDE_PATTERNS):
                    continue
                if any(word in url.lower() for word in EXCLUDE_MINUS_WORDS):
                    continue
                links.append(url)
        if not links:
            return "В поисковой выдаче не найдено подходящих сайтов (все ссылки — маркетплейсы, агрегаторы или нерелевантные ресурсы)."
        filtered_links = []
        for url in links[:10]:
            # PDF-фильтр
            if url.lower().endswith('.pdf'):
                continue
            mime, _ = mimetypes.guess_type(url)
            if mime and 'pdf' in mime:
                continue
            html = await fetch_html(url)
            if not html:
                continue
            html_lower = html.lower()
            # Минус-слова в HTML
            if any(word in html_lower for word in EXCLUDE_MINUS_WORDS):
                continue
            # Контент-фильтрация: должны быть "цена" или "руб" или "₽"
            if not ("цена" in html_lower or "руб" in html_lower or "₽" in html_lower):
                continue
            # Контакты: должен быть e-mail, phone, tel:
            if not ("@" in html_lower or "phone" in html_lower or "tel:" in html_lower):
                continue
            # Title/h1-фильтрация
            try:
                soup = BeautifulSoup(html, 'html.parser')
                title = soup.title.string.lower() if soup.title and soup.title.string else ''
                h1 = soup.h1.string.lower() if soup.h1 and soup.h1.string else ''
                if any(word in title for word in ["тендер", "pdf", "архив", "документ"]) or any(word in h1 for word in ["тендер", "pdf", "архив", "документ"]):
                    continue
            except Exception:
                pass
            # Авторанжирование по весу слов (цена, телефон, e-mail, опт, заказ)
            weight = sum(word in html_lower for word in ["цена", "телефон", "e-mail", "опт", "заказ"])
            filtered_links.append((weight, url, html))
        # Сортируем по весу (релевантности)
        filtered_links.sort(reverse=True)
        if not filtered_links:
            return "Не найдено сайтов с релевантной информацией (контент-фильтрация, PDF, минус-слова, нерелевантные заголовки)."
        results = []
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        for _, url, html in filtered_links[:10]:
            # Ограничиваем размер HTML для GPT (например, 8000 символов)
            html_short = html[:8000] if html else ''
            prompt = f"""Ты — эксперт по анализу сайтов и поиску поставщиков.

Это HTML страницы интернет-магазина. Проанализируй только основные блоки текста (без меню и футера).

Вот HTML-код страницы, которая появилась по запросу:
"{search_query}"

Проанализируй этот HTML и ответь на следующие вопросы:

1. Есть ли на странице **реальная информация о товаре**, соответствующем запросу? Если нет — напиши, что сайт не релевантен.
2. Если информация есть, то извлеки по возможности:
   – Название товара  
   – Цена (в рублях, за единицу: кг, мешок, шт и т.д.)  
   – Упаковка / фасовка (например, мешки по 25 кг)  
   – Минимальный объём заказа (если указан)  
   – Название компании или сайта  
   – Телефон, e-mail, мессенджеры  
   – Условия доставки (если есть)  
   – Регион поставки или работы компании (если указан)

⚠️ Если информация частично отсутствует, просто пропусти этот пункт, не выдумывай.

Формат ответа:
Релевантность: да / нет  
Товар: ...  
Цена: ...  
Фасовка: ...  
Минимальный объём: ...  
Компания: ...  
Контакты: ...  
Сайт: ...  
Комментарий: ... (если есть)

Вот HTML-код страницы:
{html_short}
"""
            try:
                response = await client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=800,
                    temperature=0.2,
                )
                answer = response.choices[0].message.content
                results.append(f"<b>Сайт:</b> {url}\n{answer.strip()}")
            except Exception as e:
                logger.error(f"[bot] Ошибка OpenAI: {e}")
                results.append(f"<b>Сайт:</b> {url}\n[Ошибка при обращении к GPT]")
        return "\n\n".join(results)
    
    async def _send_products_list_to_chat(self, bot, chat_id: int, tender_data: dict, page: int = 0, message_id: int = None) -> None:
        """Отправляет или обновляет список товарных позиций в чат с пагинацией"""
        # Если данные содержат номер тендера как ключ, извлекаем данные из внутреннего объекта
        if len(tender_data) == 1 and isinstance(list(tender_data.values())[0], dict):
            tender_data = list(tender_data.values())[0]
        
        product_info = tender_data.get('Продукт', {})
        print(f"[bot] tender_data['Продукт']: {product_info}")
        objects = product_info.get('ОбъектыЗак', [])
        print(f"[bot] product_info['ОбъектыЗак']: {objects}")
        
        if not objects:
            await bot.send_message(chat_id=chat_id, text="📦 Товарные позиции не найдены")
            return
        
        # Настройки пагинации
        items_per_page = 5
        total_pages = (len(objects) + items_per_page - 1) // items_per_page
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(objects))
        
        # Создаем список товарных позиций для текущей страницы
        products_text = f"📦 **Товарные позиции** (страница {page + 1} из {total_pages}):\n\n"
        
        total_cost = 0
        for i, obj in enumerate(objects[start_idx:end_idx], start_idx + 1):
            name = obj.get('Наименование', 'Без названия')
            quantity = obj.get('Количество', 0)
            unit = obj.get('ЕдИзм', 'шт')
            price = obj.get('ЦенаЕд', 0)
            cost = obj.get('Стоимость', 0)
            okpd = obj.get('ОКПД', '')
            additional_info = obj.get('ДопИнфо', '')
            date = obj.get('Дата', '')
            
            products_text += f"{i}. **{name}**\n"
            products_text += f"   📊 Количество: {quantity} {unit}\n"
            products_text += f"   💰 Цена за ед.: {format_price(price)}\n"
            products_text += f"   💵 Стоимость: {format_price(cost)}\n"
            if okpd:
                products_text += f"   🏷️ ОКПД: {okpd}\n"
            if additional_info:
                short_info = additional_info[:80] + "..." if len(additional_info) > 80 else additional_info
                products_text += f"   ℹ️ Доп. инфо: {short_info}\n"
            if date:
                products_text += f"   📅 Дата: {format_date(date)}\n"
            products_text += "\n"
            
            total_cost += cost
        
        # Добавляем общую стоимость всех позиций
        total_all_cost = sum(obj.get('Стоимость', 0) for obj in objects)
        products_text += f"**Общая стоимость всех позиций: {format_price(total_all_cost)}**"
        
        # Создаем кнопки навигации
        keyboard = []
        nav_buttons = []
        
        if total_pages > 1:
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"products_page_{page-1}"))
            
            nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="current_page"))
            
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"products_page_{page+1}"))
            
            if nav_buttons:
                keyboard.append(nav_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        if message_id is not None:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=products_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            await bot.send_message(chat_id=chat_id, text=products_text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _send_documents_list_with_download(self, bot, chat_id: int, tender_data: dict, reg_number: str, page: int = 0) -> None:
        """Отправляет список документов с возможностью скачивания и пагинацией"""
        # Если данные содержат номер тендера как ключ, извлекаем документы из внутреннего объекта
        if len(tender_data) == 1 and isinstance(list(tender_data.values())[0], dict):
            tender_data = list(tender_data.values())[0]
        
        documents = tender_data.get('Документы', [])
        
        if not documents:
            await bot.send_message(chat_id=chat_id, text="📄 Документы не найдены")
            return
        
        # Настройки пагинации
        items_per_page = 8
        total_pages = (len(documents) + items_per_page - 1) // items_per_page
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(documents))
        
        # Создаем список документов для текущей страницы
        docs_text = f"📄 **Документы тендера** (страница {page + 1} из {total_pages}):\n\n"
        
        for i, doc in enumerate(documents[start_idx:end_idx], start_idx + 1):
            name = doc.get('Название', 'Без названия')
            date = doc.get('ДатаРазм', '')
            files = doc.get('Файлы', [])
            
            docs_text += f"{i}. **{name}**\n"
            if date:
                docs_text += f"   📅 Дата: {format_date(date)}\n"
            if files:
                docs_text += f"   📎 Файлов: {len(files)}\n"
            docs_text += "\n"
        
        docs_text += "💾 **Скачать все документы:**"
        
        # Создаем кнопки навигации и скачивания
        keyboard = []
        
        # Кнопки навигации
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"docs_page_{reg_number}_{page-1}"))
            
            nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="current_page"))
            
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"docs_page_{reg_number}_{page+1}"))
            
            if nav_buttons:
                keyboard.append(nav_buttons)
        
        # Кнопка скачивания
        keyboard.append([InlineKeyboardButton("📥 Скачать документы", callback_data=f"download_{reg_number}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await bot.send_message(chat_id=chat_id, text=docs_text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _send_detailed_info_to_chat(self, bot, chat_id: int, tender_info: dict) -> None:
        """Отправляет подробную информацию о тендере"""
        detailed_text = f"""
🏢 **Подробная информация о тендере**

🔍 **Детали закупки:**
• **Способ закупки:** {tender_info['procurement_type']}
• **Место поставки:** {tender_info['delivery_place']}
• **Срок поставки:** {tender_info['delivery_terms']}
• **Обеспечение заявки:** {tender_info['guarantee_amount']}
• **Источник финансирования:** {tender_info['funding_source']}

🌍 **Региональная информация:**
• **Регион:** {tender_info['region']}
• **Федеральный закон:** {tender_info['federal_law']}-ФЗ

🏢 **Электронная торговая площадка:**
• **Название:** {tender_info['etp_name']}
• **Сайт:** {tender_info['etp_url']}

📞 **Контактная информация:**
• **Ответственное лицо:** {tender_info['contact_person']}
• **Телефон:** {format_phone(tender_info['contact_phone'])}
• **Email:** {tender_info['contact_email']}

💳 **Финансовые детали:**
• **ИКЗ:** {tender_info['ikz']}
• **Аванс:** {tender_info['advance_percent']}%
• **Обеспечение исполнения:** {tender_info['execution_amount']}
• **Банковское сопровождение:** {tender_info['bank_support']}
        """
        
        await bot.send_message(chat_id=chat_id, text=detailed_text, parse_mode='Markdown')
    
    async def _update_documents_message(self, bot, chat_id: int, message_id: int, tender_data: dict, reg_number: str, page: int) -> None:
        """Обновляет сообщение с документами для пагинации"""
        # Если данные содержат номер тендера как ключ, извлекаем документы из внутреннего объекта
        if len(tender_data) == 1 and isinstance(list(tender_data.values())[0], dict):
            tender_data = list(tender_data.values())[0]
        
        documents = tender_data.get('Документы', [])
        
        if not documents:
            await bot.edit_message_text(
                chat_id=chat_id, 
                message_id=message_id, 
                text="📄 Документы не найдены"
            )
            return
        
        # Настройки пагинации
        items_per_page = 8
        total_pages = (len(documents) + items_per_page - 1) // items_per_page
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(documents))
        
        # Создаем список документов для текущей страницы
        docs_text = f"📄 **Документы тендера** (страница {page + 1} из {total_pages}):\n\n"
        
        for i, doc in enumerate(documents[start_idx:end_idx], start_idx + 1):
            name = doc.get('Название', 'Без названия')
            date = doc.get('ДатаРазм', '')
            files = doc.get('Файлы', [])
            
            docs_text += f"{i}. **{name}**\n"
            if date:
                docs_text += f"   📅 Дата: {format_date(date)}\n"
            if files:
                docs_text += f"   📎 Файлов: {len(files)}\n"
            docs_text += "\n"
        
        docs_text += "💾 **Скачать все документы:**"
        
        # Создаем кнопки навигации и скачивания
        keyboard = []
        
        # Кнопки навигации
        if total_pages > 1:
            nav_buttons = []
            if page > 0:
                nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"docs_page_{reg_number}_{page-1}"))
            
            nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="current_page"))
            
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"docs_page_{reg_number}_{page+1}"))
            
            if nav_buttons:
                keyboard.append(nav_buttons)
        
        # Кнопка скачивания
        keyboard.append([InlineKeyboardButton("📥 Скачать документы", callback_data=f"download_{reg_number}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=docs_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    def setup_handlers(self):
        """Настраивает обработчики команд и сообщений"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("cleanup", self.cleanup_command))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    def run(self):
        try:
            self.app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
            self.setup_handlers()
            logger.info("🚀 TenderBot запущен")
            print("🤖 TenderBot запущен и готов к работе!")
            print("📝 Логи сохраняются в файл:", LOG_FILE)
            self.app.run_polling()
        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота: {e}")
            raise

    async def _generate_supplier_queries(self, formatted_info):
        # Пример: возвращаем список поисковых запросов на основе анализа
        # Можно сделать умнее, если в анализе есть ключевые слова
        subject = formatted_info.get('subject', '')
        return [subject] if subject else []

# Создаем и запускаем бота
if __name__ == "__main__":
    bot = TenderBot()
    bot.run()
