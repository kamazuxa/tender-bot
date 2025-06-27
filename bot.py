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
import functools
import time
from typing import Optional, Dict, Any, Callable
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

# Кэш для результатов анализа
ANALYSIS_CACHE = {}
CACHE_TTL = 3600  # 1 час

# Retry настройки
MAX_RETRIES = 3
RETRY_DELAY = 1  # секунды

def retry_on_error(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """Декоратор для retry-логики"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"[retry] Попытка {attempt + 1}/{max_retries} не удалась: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay * (2 ** attempt))  # Экспоненциальная задержка
            logger.error(f"[retry] Все попытки исчерпаны: {last_exception}")
            raise last_exception
        return wrapper
    return decorator

def get_cache_key(tender_data: Dict, files: list) -> str:
    """Генерирует ключ кэша для анализа"""
    import hashlib
    tender_str = json.dumps(tender_data, sort_keys=True)
    files_str = json.dumps([f.get('path', '') for f in files], sort_keys=True)
    return hashlib.md5((tender_str + files_str).encode()).hexdigest()

def get_cached_analysis(cache_key: str) -> Optional[Dict]:
    """Получает результат анализа из кэша"""
    if cache_key in ANALYSIS_CACHE:
        timestamp, result = ANALYSIS_CACHE[cache_key]
        if time.time() - timestamp < CACHE_TTL:
            logger.info(f"[cache] Найден кэшированный результат для {cache_key}")
            return result
        else:
            del ANALYSIS_CACHE[cache_key]
    return None

def cache_analysis_result(cache_key: str, result: Dict):
    """Сохраняет результат анализа в кэш"""
    ANALYSIS_CACHE[cache_key] = (time.time(), result)
    logger.info(f"[cache] Результат сохранен в кэш: {cache_key}")

def safe_get_message(update: Update) -> Optional[Any]:
    """Безопасно получает сообщение из update"""
    if update.message:
        return update.message
    elif update.callback_query and update.callback_query.message:
        return update.callback_query.message
    return None

def validate_user_session(user_id: int, user_sessions: Dict, required_status: str = None) -> tuple[bool, Optional[Dict]]:
    """Проверяет валидность сессии пользователя"""
    if user_id not in user_sessions:
        return False, None
    
    session = user_sessions[user_id]
    
    if required_status and session.get('status') != required_status:
        return False, session
    
    return True, session

async def handle_session_error(query, error_msg: str = "❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново."):
    """Обрабатывает ошибки сессии"""
    try:
        await query.edit_message_text(error_msg)
    except Exception as e:
        logger.warning(f"[bot] Не удалось отправить сообщение об ошибке: {e}")

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
        """Обрабатывает входящие сообщения"""
        user_id = update.effective_user.id
        message_text = update.message.text.strip()
        
        logger.info(f"[bot] Получено сообщение от {user_id}: {message_text}...")
        
        try:
            # Показываем что бот печатает (необязательно)
            try:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            except Exception as e:
                logger.warning(f"[bot] Не удалось отправить chat_action: {e}")
                # Продолжаем работу без chat_action
        except Exception as e:
            logger.error(f"[bot] Ошибка при обработке chat_action: {e}")
        
        # Инициализируем сессию пользователя если её нет
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {
                'status': 'waiting_for_tender',
                'tender_data': None,
                'files': None,
                'search_queries': None
            }
        
        # Обрабатываем команды
        if message_text.startswith('/'):
            if message_text == '/start':
                await self.start_command(update, context)
            elif message_text == '/help':
                await self.help_command(update, context)
            elif message_text == '/status':
                await self.status_command(update, context)
            elif message_text == '/cleanup':
                await self.cleanup_command(update, context)
            else:
                await update.message.reply_text("❌ Неизвестная команда. Используйте /help для списка команд.")
            return
        
        # Проверяем статус пользователя
        session = self.user_sessions[user_id]
        
        if session['status'] == 'waiting_for_tender':
            # Ожидаем номер тендера
            await update.message.reply_text("🔍 Ищу тендер...")
            
            try:
                # Извлекаем номер тендера
                tender_number = extract_tender_number(message_text)
                if not tender_number:
                    await update.message.reply_text("❌ Не удалось извлечь номер тендера. Пожалуйста, отправьте корректный номер.")
                    return
                
                # Получаем данные тендера
                tender_info = await damia_client.get_tender_info(tender_number)
                if not tender_info:
                    await update.message.reply_text("❌ Тендер не найден или произошла ошибка при получении данных.")
                    return
                
                # Обновляем статус
                session['status'] = 'tender_found'
                session['tender_data'] = tender_info
                
                # Отправляем информацию о тендере
                await self._send_tender_info(update, tender_info, tender_number)
                
            except Exception as e:
                logger.error(f"[bot] Ошибка при обработке номера тендера: {e}")
                await update.message.reply_text(f"❌ Произошла ошибка при обработке номера тендера: {str(e)}")
                
        elif session['status'] == 'tender_found':
            await update.message.reply_text("📋 Тендер уже найден. Используйте кнопки для навигации или отправьте новый номер тендера.")
            
        elif session['status'] == 'ready_for_analysis':
            await update.message.reply_text("🤖 Анализ уже готов. Используйте кнопки для навигации или отправьте новый номер тендера.")
            
        elif session['status'] == 'completed':
            await update.message.reply_text("✅ Анализ завершён. Отправьте новый номер тендера для анализа.")
            
        else:
            await update.message.reply_text("❓ Неизвестный статус. Отправьте номер тендера для начала работы.")
    
    async def _send_tender_info(self, update: Update, tender_info: dict, reg_number: str) -> None:
        """Отправляет основную информацию о тендере"""
        try:
            # --- ВСТАВКА: распаковка по номеру тендера ---
            if tender_info and len(tender_info) == 1 and isinstance(list(tender_info.values())[0], dict):
                tender_info = list(tender_info.values())[0]
            # --- КОНЕЦ ВСТАВКИ ---
            
            logger.info(f"[bot] Ответ DaMIA: {tender_info}")
            
            if not tender_info:
                await update.message.reply_text(
                    f"❌ Не удалось найти тендер с номером {reg_number}.\n"
                    "Проверьте правильность номера или попробуйте позже."
                )
                return
                
            formatted_data = damia_client.format_tender_info(tender_info)
            user_id = update.effective_user.id
            
            # Обновляем сессию пользователя
            if user_id in self.user_sessions:
                self.user_sessions[user_id]['tender_data'] = tender_info
                self.user_sessions[user_id]['formatted_info'] = formatted_data
                self.user_sessions[user_id]['status'] = 'ready_for_analysis'
            
            # Преобразуем словарь в строку для отображения
            formatted_info = f"""
📋 **Информация о тендере**

📊 **Статус:** {formatted_data.get('status', 'Не указан')}
📋 **Федеральный закон:** {formatted_data.get('federal_law', 'Не указан')}-ФЗ
🏢 **Заказчик:** {formatted_data.get('customer', 'Не указан')}
📝 **ИНН:** {formatted_data.get('customer_inn', 'Не указан')}
📍 **Адрес:** {formatted_data.get('customer_address', 'Не указан')}
📄 **Предмет поставки:** {formatted_data.get('subject', 'Не указан')}
💰 **Цена:** {formatted_data.get('price', 'Не указана')}
📅 **Дата публикации:** {formatted_data.get('publication_date', 'Не указана')}
⏰ **Срок подачи до:** {formatted_data.get('submission_deadline', 'Не указана')}
📍 **Место поставки:** {formatted_data.get('delivery_place', 'Не указано')}
🏛️ **ЭТП:** {formatted_data.get('etp_name', 'Не указана')}
📞 **Контакты:** {formatted_data.get('contact_person', 'Не указано')} | {formatted_data.get('contact_phone', 'Не указан')}
📧 **Email:** {formatted_data.get('contact_email', 'Не указан')}
"""
            
            # Создаем клавиатуру с кнопками
            keyboard = [
                [InlineKeyboardButton("📋 Подробная информация", callback_data="detailed_info")],
                [InlineKeyboardButton("📦 Товарные позиции", callback_data="products")],
                [InlineKeyboardButton("📄 Документы", callback_data="documents")],
                [InlineKeyboardButton("🤖 Детальный анализ", callback_data="analyze")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Разбиваем длинную информацию на части
            max_length = 4000  # Оставляем запас для Telegram
            if len(formatted_info) > max_length:
                # Разбиваем на части
                parts = []
                current_part = ""
                lines = formatted_info.split('\n')
                
                for line in lines:
                    if len(current_part) + len(line) + 1 > max_length:
                        if current_part:
                            parts.append(current_part.strip())
                        current_part = line
                    else:
                        current_part += '\n' + line if current_part else line
                
                if current_part:
                    parts.append(current_part.strip())
                
                # Отправляем первую часть с кнопками
                await update.message.reply_text(
                    f"📋 **Информация о тендере** (часть 1 из {len(parts)}):\n\n{parts[0]}",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
                
                # Отправляем остальные части
                for i, part in enumerate(parts[1:], 2):
                    await update.message.reply_text(
                        f"📋 **Продолжение информации** (часть {i} из {len(parts)}):\n\n{part}",
                        parse_mode='Markdown'
                    )
            else:
                # Отправляем основную информацию одним сообщением
                await update.message.reply_text(
                    f"📋 **Информация о тендере**\n\n{formatted_info}",
                    parse_mode='Markdown',
                    reply_markup=reply_markup
                )
            
        except Exception as e:
            logger.error(f"[bot] Ошибка при отправке информации о тендере: {e}")
            try:
                await update.message.reply_text(
                    f"❌ Произошла ошибка при отображении информации о тендере: {str(e)}\n"
                    "Попробуйте позже или обратитесь к администратору."
                )
            except Exception as send_error:
                logger.error(f"[bot] Не удалось отправить сообщение об ошибке: {send_error}")
    
    async def _analyze_documents(self, tender_data, files, update=None, chat_id=None, bot=None):
        # Проверяем кэш
        cache_key = get_cache_key(tender_data, files)
        cached_result = get_cached_analysis(cache_key)
        if cached_result:
            logger.info("[bot] Возвращаем кэшированный результат анализа")
            return cached_result
        
        # Новый экспертный промпт для анализа и генерации поисковых запросов
        async def progress_callback(message: str):
            """Callback для отображения прогресса"""
            try:
                if update and hasattr(update, 'edit_message_text'):
                    await update.edit_message_text(message)
                elif bot and chat_id:
                    await bot.send_message(chat_id=chat_id, text=message)
            except Exception as e:
                logger.warning(f"[bot] Не удалось отправить прогресс: {e}")
        
        try:
            analysis_result = await analyzer.analyze_tender_documents(
                tender_data, files, progress_callback=progress_callback
            )
            
            if analysis_result:
                # Сохраняем в кэш
                cache_analysis_result(cache_key, analysis_result)
                
                # Сохраняем поисковые запросы в сессии пользователя
                if update and hasattr(update, 'from_user'):
                    user_id = update.from_user.id
                    if user_id in self.user_sessions:
                        self.user_sessions[user_id]['search_queries'] = analysis_result.get('search_queries', {})
                
                return analysis_result
            else:
                logger.error("[bot] Анализатор вернул пустой результат")
                return None
                
        except Exception as e:
            logger.error(f"[bot] Ошибка при анализе документов: {e}")
            return None
    
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
        # --- Вырезаем раздел 'Поисковые запросы' из summary для пользователя ---
        import re
        summary_clean = re.split(r'Поисковые запросы\s*:?', summary, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        # Разбиваем длинный анализ на части
        if len(summary_clean) > 4000:
            parts = [summary_clean[i:i+4000] for i in range(0, len(summary_clean), 4000)]
            for i, part in enumerate(parts):
                if i == 0:
                    await bot.send_message(chat_id=chat_id, text=f"🤖 **Анализ тендера** (часть {i+1}/{len(parts)}):\n\n{part}", parse_mode='Markdown')
                else:
                    await bot.send_message(chat_id=chat_id, text=f"🤖 **Продолжение анализа** (часть {i+1}/{len(parts)}):\n\n{part}", parse_mode='Markdown')
        else:
            await bot.send_message(chat_id=chat_id, text=f"🤖 **Анализ тендера:**\n\n{summary_clean}", parse_mode='Markdown')
        # --- Сохраняем поисковые запросы GPT для дальнейшего использования ---
        search_queries = analysis_result.get('search_queries', {})
        for user_id, session in self.user_sessions.items():
            if session.get('status') in ['ready_for_analysis', 'completed']:
                session['search_queries'] = search_queries
        if not search_queries:
            await bot.send_message(chat_id=chat_id, text="❌ Не удалось выделить товарные позиции из анализа. Попробуйте другой тендер или обратитесь к администратору.")
            return
        # --- Показываем только одну кнопку '🔎 Найти поставщиков' ---
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
        user_id = query.from_user.id
        
        try:
            await query.answer()  # Убираем "часики" у кнопки
        except Exception as e:
            logger.warning(f"[bot] Не удалось ответить на callback: {e}")
        
        try:
            logger.info(f"[bot] Обрабатываем callback: {query.data} от пользователя {user_id}")
            
            if query.data == "help":
                await self.help_command(update, context)
            elif query.data == "status":
                await self.status_command(update, context)
            elif query.data == "cleanup":
                await self.cleanup_command(update, context)
            elif query.data == "products":
                # Обработка кнопки "Товарные позиции"
                valid, session = validate_user_session(user_id, self.user_sessions, 'ready_for_analysis')
                if not valid:
                    await handle_session_error(query)
                    return
                tender_data = session['tender_data']
                # Отправляем новое сообщение вместо редактирования
                await self._send_products_list_to_chat(context.bot, query.message.chat_id, tender_data, page=0)
            elif query.data == "documents":
                # Обработка кнопки "Документы"
                valid, session = validate_user_session(user_id, self.user_sessions, 'ready_for_analysis')
                if not valid:
                    await handle_session_error(query)
                    return
                # Получаем данные из сессии
                tender_data = session['tender_data']
                reg_number = extract_tender_number(str(tender_data))
                if not reg_number:
                    await query.edit_message_text("❌ Не удалось извлечь номер тендера.")
                    return
                # Отправляем новое сообщение вместо редактирования
                await self._send_documents_list_with_download(
                    context.bot, 
                    query.message.chat_id, 
                    tender_data, 
                    reg_number, 
                    page=0
                )
            elif query.data == "detailed_info":
                # Обработка кнопки "Подробная информация"
                valid, session = validate_user_session(user_id, self.user_sessions, 'ready_for_analysis')
                if not valid:
                    await handle_session_error(query)
                    return
                # Получаем данные из сессии
                tender_data = session['tender_data']
                # Отправляем подробную информацию
                await self._send_detailed_info_to_chat(context.bot, query.message.chat_id, tender_data)
            elif query.data == "analyze":
                # Обработка кнопки "Детальный анализ"
                valid, session = validate_user_session(user_id, self.user_sessions, 'ready_for_analysis')
                if not valid:
                    await handle_session_error(query)
                    return
                
                # Получаем данные из сессии
                tender_data = session['tender_data']
                
                await context.bot.send_message(chat_id=query.message.chat_id, text="🤖 Начинаю анализ документов...")
                
                try:
                    # Скачиваем документы
                    reg_number = extract_tender_number(str(tender_data))
                    if not reg_number:
                        await query.edit_message_text("❌ Не удалось извлечь номер тендера для скачивания документов.")
                        return
                        
                    files = await downloader.download_documents(tender_data, reg_number)
                    if not files or files.get('success', 0) == 0:
                        await query.edit_message_text("❌ Не удалось скачать документы для анализа.")
                        return
                        
                    session['files'] = files.get('files', [])
                    
                    # Анализируем документы
                    analysis_result = await self._analyze_documents(
                        tender_data, 
                        files.get('files', []), 
                        update=query, 
                        chat_id=query.message.chat_id, 
                        bot=context.bot
                    )
                    
                    if analysis_result:
                        await self._send_analysis_to_chat(context.bot, query.message.chat_id, analysis_result)
                        session['status'] = 'completed'
                    else:
                        await query.edit_message_text("❌ Не удалось проанализировать документы.")
                        
                except Exception as e:
                    logger.error(f"[bot] Ошибка при анализе: {e}")
                    await query.edit_message_text(f"❌ Произошла ошибка при анализе: {str(e)}")
            elif query.data.startswith("products_page_"):
                try:
                    page = int(query.data.split("_")[2])
                except Exception:
                    page = 0
                valid, session = validate_user_session(user_id, self.user_sessions, 'ready_for_analysis')
                if not valid:
                    await handle_session_error(query)
                    return
                tender_data = session['tender_data']
                # Навигация: отправляем новое сообщение вместо редактирования
                logger.info(f"[bot] Навигация по товарам: page={page}")
                await self._send_products_list_to_chat(context.bot, query.message.chat_id, tender_data, page=page)
            elif query.data == "current_page":
                await query.answer("Текущая страница")
            elif query.data.startswith("documents_page_"):
                page = int(query.data.split('_')[-1])
                valid, session = validate_user_session(user_id, self.user_sessions, 'ready_for_analysis')
                if not valid:
                    await handle_session_error(query)
                    return
                tender_data = session['tender_data']
                reg_number = extract_tender_number(str(tender_data))
                if not reg_number:
                    await query.edit_message_text("❌ Не удалось извлечь номер тендера.")
                    return
                # Отправляем новое сообщение вместо редактирования
                await self._send_documents_list_with_download(
                    context.bot, 
                    query.message.chat_id, 
                    tender_data, 
                    reg_number, 
                    page
                )
            elif query.data.startswith("download_"):
                file_id = query.data.split('_', 1)[1]
                valid, session = validate_user_session(user_id, self.user_sessions, 'ready_for_analysis')
                if not valid:
                    await handle_session_error(query)
                    return
                tender_data = session['tender_data']
                reg_number = extract_tender_number(str(tender_data))
                if not reg_number:
                    await query.edit_message_text("❌ Не удалось извлечь номер тендера.")
                    return
                    
                try:
                    file_path = downloader.get_file_path(reg_number, file_id)
                    if file_path and os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            await context.bot.send_document(
                                chat_id=query.message.chat_id,
                                document=f,
                                filename=os.path.basename(file_path)
                            )
                    else:
                        await query.edit_message_text("❌ Файл не найден.")
                except Exception as e:
                    logger.error(f"[bot] Ошибка при отправке файла: {e}")
                    await query.edit_message_text(f"❌ Ошибка при отправке файла: {str(e)}")
            elif query.data == "find_suppliers":
                # После анализа: выводим кнопки по всем товарным позициям (только по GPT)
                valid, session = validate_user_session(user_id, self.user_sessions, 'ready_for_analysis')
                if not valid:
                    await handle_session_error(query)
                    return
                search_queries = session.get('search_queries', {})
                if not search_queries:
                    await query.edit_message_text("В этом тендере отсутствуют товарные позиции (ИИ не выделил их из анализа). Возможно, это закупка услуг или данные не заполнены.")
                    return
                keyboard = []
                for idx, (position, query_text) in enumerate(search_queries.items()):
                    keyboard.append([InlineKeyboardButton(position, callback_data=f"find_supplier_{idx}")])
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="Выберите товарную позицию для поиска поставщика:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            elif query.data.startswith("find_supplier_"):
                valid, session = validate_user_session(user_id, self.user_sessions, 'ready_for_analysis')
                if not valid:
                    await handle_session_error(query)
                    return
                idx = int(query.data.split('_')[-1])
                search_queries = session.get('search_queries', {})
                if idx >= len(search_queries):
                    await query.edit_message_text("❌ Позиция не найдена.")
                    return
                position = list(search_queries.keys())[idx]
                search_query = list(search_queries.values())[idx]
                logger.info(f"[bot] Поисковый запрос для SerpAPI по позиции '{position}': {search_query}")
                await query.edit_message_text(f"🔎 Ищу поставщиков по позиции: {position} (по запросу: {search_query})...")
                
                try:
                    search_results = await self._search_suppliers_serpapi(search_query)
                    gpt_result = await self._extract_suppliers_gpt_ranked(search_query, search_results)
                    await context.bot.send_message(chat_id=query.message.chat_id, text=gpt_result, parse_mode='HTML')
                except Exception as e:
                    logger.error(f"[bot] Ошибка при поиске поставщиков: {e}")
                    await query.edit_message_text(f"❌ Произошла ошибка при поиске поставщиков: {str(e)}")
        except Exception as e:
            logger.error(f"[bot] Ошибка при обработке callback: {e}")
    
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
                "num": 20
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
        # Проверяем все сайты из выдачи (до 40), а не только первые 10
        for url in links:
            logger.info(f"[bot] Проверяем сайт: {url}")
            
            # PDF-фильтр
            if url.lower().endswith('.pdf'):
                logger.info(f"[bot] ❌ {url} — отсеян: PDF файл")
                continue
            mime, _ = mimetypes.guess_type(url)
            if mime and 'pdf' in mime:
                logger.info(f"[bot] ❌ {url} — отсеян: PDF mime-type")
                continue
                
            html = await fetch_html(url)
            if not html:
                logger.info(f"[bot] ❌ {url} — отсеян: не удалось скачать HTML")
                continue
                
            html_lower = html.lower()
            
            # Минус-слова в HTML
            minus_words_found = [word for word in EXCLUDE_MINUS_WORDS if word in html_lower]
            if minus_words_found:
                logger.info(f"[bot] ❌ {url} — отсеян: найдены минус-слова: {minus_words_found}")
                continue
                
            # Ослабленная контент-фильтрация: хотя бы одно из условий
            has_price = "цена" in html_lower or "руб" in html_lower or "₽" in html_lower
            has_contacts = "@" in html_lower or "phone" in html_lower or "tel:" in html_lower
            has_keywords = any(word in html_lower for word in ["опт", "заказ", "поставка", "купить", "продажа"])
            
            if not (has_price or has_contacts or has_keywords):
                logger.info(f"[bot] ❌ {url} — отсеян: нет ни цен, ни контактов, ни ключевых слов")
                continue
            else:
                logger.info(f"[bot] ✅ {url} — прошёл фильтрацию: цена={has_price}, контакты={has_contacts}, ключевые слова={has_keywords}")
                
            # Title/h1-фильтрация
            try:
                soup = BeautifulSoup(html, 'html.parser')
                title = soup.title.string.lower() if soup.title and soup.title.string else ''
                h1 = soup.h1.string.lower() if soup.h1 and soup.h1.string else ''
                bad_title_words = [word for word in ["тендер", "pdf", "архив", "документ"] if word in title]
                bad_h1_words = [word for word in ["тендер", "pdf", "архив", "документ"] if word in h1]
                if bad_title_words or bad_h1_words:
                    logger.info(f"[bot] ❌ {url} — отсеян: плохие заголовки: title={bad_title_words}, h1={bad_h1_words}")
                    continue
            except Exception as e:
                logger.warning(f"[bot] ⚠️ {url} — ошибка при проверке заголовков: {e}")
                pass
                
            # Ослабленное авторанжирование по весу слов (30% релевантности)
            relevant_words = ["цена", "телефон", "e-mail", "опт", "заказ", "поставка", "купить", "продажа", "контакты"]
            found_words = [word for word in relevant_words if word in html_lower]
            weight = len(found_words)
            max_possible_weight = len(relevant_words)
            relevance_percent = (weight / max_possible_weight) * 100
            
            # Разрешаем сайты с 30% релевантности
            if relevance_percent >= 30:
                logger.info(f"[bot] ✅ {url} — релевантность {relevance_percent:.1f}% (найдены слова: {found_words})")
                filtered_links.append((weight, url, html, relevance_percent))
            else:
                logger.info(f"[bot] ❌ {url} — отсеян: низкая релевантность {relevance_percent:.1f}% (найдены слова: {found_words})")
                
        # Сортируем по весу (релевантности)
        filtered_links.sort(key=lambda x: x[3], reverse=True)  # сортируем по проценту релевантности
        if not filtered_links:
            return "Не найдено сайтов с релевантной информацией (контент-фильтрация, PDF, минус-слова, нерелевантные заголовки)."
            
        logger.info(f"[bot] Найдено {len(filtered_links)} подходящих сайтов из {len(links)} проверенных")
        for i, (weight, url, html, relevance) in enumerate(filtered_links[:10]):
            logger.info(f"[bot] Топ {i+1}: {url} (релевантность: {relevance:.1f}%)")
            
        results = []
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        # Отправляем в ИИ максимум 10 лучших сайтов
        for weight, url, html, relevance in filtered_links[:10]:
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
                results.append(f"<b>Сайт:</b> {url} (релевантность: {relevance:.1f}%)\n{answer.strip()}")
            except Exception as e:
                logger.error(f"[bot] Ошибка OpenAI: {e}")
                results.append(f"<b>Сайт:</b> {url} (релевантность: {relevance:.1f}%)\n[Ошибка при обращении к GPT]")
        return "\n\n".join(results)
    
    async def _send_products_list_to_chat(self, bot, chat_id: int, tender_data: dict, page: int = 0) -> None:
        """Отправляет список товарных позиций с пагинацией"""
        # Если данные содержат номер тендера как ключ, извлекаем продукты из внутреннего объекта
        if len(tender_data) == 1 and isinstance(list(tender_data.values())[0], dict):
            tender_data = list(tender_data.values())[0]
        
        products = tender_data.get('Продукт', {}).get('ОбъектыЗак', [])
        
        if not products:
            await bot.send_message(chat_id=chat_id, text="📦 Товарные позиции не найдены")
            return
        
        # Настройки пагинации
        items_per_page = 5
        total_pages = (len(products) + items_per_page - 1) // items_per_page
        start_idx = page * items_per_page
        end_idx = min(start_idx + items_per_page, len(products))
        
        # Создаем список товаров для текущей страницы
        products_text = f"📦 **Товарные позиции** (страница {page + 1} из {total_pages}):\n\n"
        
        for i, product in enumerate(products[start_idx:end_idx], start_idx + 1):
            name = product.get('Наименование', 'Без названия')
            quantity = product.get('Количество', 0)
            unit = product.get('ЕдИзм', '')
            price = product.get('ЦенаЕд', 0)
            total_cost = product.get('Стоимость', 0)
            okpd = product.get('ОКПД', '')
            
            products_text += f"{i}. **{name}**\n"
            products_text += f"   📊 Количество: {quantity} {unit}\n"
            products_text += f"   💰 Цена за единицу: {format_price(price)} руб.\n"
            products_text += f"   💵 Общая стоимость: {format_price(total_cost)} руб.\n"
            if okpd:
                products_text += f"   🏷️ ОКПД: {okpd}\n"
            products_text += "\n"
        
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
        
        # Всегда отправляем новое сообщение
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
                nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"documents_page_{page-1}"))
            
            nav_buttons.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="current_page"))
            
            if page < total_pages - 1:
                nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"documents_page_{page+1}"))
            
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
            logger.error(f"❌ Ошибка запуска бота {e}")
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