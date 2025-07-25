import logging
logging.basicConfig(level=logging.INFO)
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters
)
from config import TELEGRAM_TOKEN, LOG_LEVEL, LOG_FILE, OPENAI_API_KEY, OPENAI_MODEL
from downloader import downloader
from analyzer import analyzer
from tender_history import TenderHistoryAnalyzer
# Импорты для API проверки контрагентов
from fssp_api import fssp_client
import os
import re
import zipfile
import tempfile
import json
import openai
from typing import Optional, Dict, Any, Callable, Union, List
try:
    import httpx
except ImportError:
    httpx = None
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None
from exportbase_api import get_company_by_inn
from email_generator import generate_supplier_email
from keyboards import (
    main_keyboard, analyze_keyboard, search_keyboard, supplier_keyboard,
    analytics_keyboard, profile_keyboard, help_keyboard, locked_keyboard,
    analyze_suggest_keyboard, supplier_suggest_keyboard, search_suggest_keyboard,
    back_to_menu_keyboard, BACK_CB, analytics_suggest_keyboard, profile_suggest_keyboard,
    email_suggest_keyboard, history_keyboard, HISTORY_REPEAT_CB
)
from texts import (
    welcome_text, analyze_tender_text, search_tender_text, check_company_text,
    analytics_text, profile_text, help_text, locked_text,
    inn_invalid_text, tender_invalid_text, keywords_invalid_text,
    success_analyze_text, success_supplier_text, success_search_text,
    suggest_supplier_check_text, suggest_tender_search_text, suggest_analyze_text,
    back_to_menu_text, success_analytics_text, success_profile_text, success_email_text,
    analytics_invalid_text, profile_invalid_text, email_invalid_text,
    tooltip_first_start, tooltip_error_repeat
)
from states import BotState
from utils.validators import is_valid_inn, is_valid_tender_number, is_valid_keywords, extract_tender_number
import importlib
company_handlers = importlib.import_module('handlers.company_handlers')
analyze_handlers = importlib.import_module('handlers.analyze_handlers')
history_handlers = importlib.import_module('handlers.history_handlers')
from tenderguru_api import TenderGuruAPI, TENDERGURU_API_CODE, format_tender_history
import functools
import time
from handlers.analyze_handlers import handle_tender_card_callback
from handlers.history_handlers import analyze_found_tender_callback

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

def escape_markdown(text: str) -> str:
    """Экранирует специальные символы Markdown для Telegram"""
    if not text:
        return text
    
    # Символы, которые нужно экранировать в Markdown
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

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

def validate_user_session(user_id: int, user_sessions: Dict, required_status: Union[str, List[str]] = None) -> tuple[bool, Optional[Dict]]:
    """Проверяет валидность сессии пользователя"""
    if user_id not in user_sessions:
        return False, None
    
    session = user_sessions[user_id]
    
    if required_status:
        if isinstance(required_status, list):
            # Если передали список статусов, проверяем что текущий статус в списке
            if session.get('status') not in required_status:
                return False, session
        else:
            # Если передали строку, проверяем точное совпадение
            if session.get('status') != required_status:
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
    """Преобразует дату из формата YYYY-MM-DD в "Дата месяц год" на русском языке"""
    if not date_str or date_str == 'Не указана':
        return 'Не указана'
    
    try:
        # Словарь месяцев на русском языке
        months = {
            '01': 'января', '02': 'февраля', '03': 'марта', '04': 'апреля',
            '05': 'мая', '06': 'июня', '07': 'июля', '08': 'августа',
            '09': 'сентября', '10': 'октября', '11': 'ноября', '12': 'декабря'
        }
        
        # Разбираем дату
        parts = date_str.split('-')
        if len(parts) == 3:
            year = parts[0]
            month = parts[1]
            day = parts[2]
            
            # Убираем ведущий ноль из дня
            day = str(int(day))
            
            # Получаем название месяца
            month_name = months.get(month, month)
            
            return f"{day} {month_name} {year}"
        
        return date_str
    except Exception:
        return date_str

def format_phone(phone_raw):
    """Форматирует телефон в кликабельный вид для Telegram +7XXXXXXXXXX"""
    if not phone_raw or phone_raw == 'Не указан':
        return 'Не указан'
    
    # Убираем все нецифровые символы
    digits = re.sub(r'\D', '', str(phone_raw))
    
    # Если номер начинается с 7 и имеет 11 цифр
    if digits.startswith('7') and len(digits) == 11:
        return f"+{digits}"
    
    # Если номер начинается с 8 и имеет 11 цифр (старый формат)
    elif digits.startswith('8') and len(digits) == 11:
        return f"+7{digits[1:]}"
    
    # Если номер имеет 10 цифр (без кода страны)
    elif len(digits) == 10:
        return f"+7{digits}"
    
    # Если номер имеет 7 цифр (городской)
    elif len(digits) == 7:
        return f"+7495{digits}"
    
    # Если ничего не подходит, возвращаем как есть
    return phone_raw

class TenderBot:
    def __init__(self):
        self.app = None
        self.user_sessions = {}  # Для хранения состояния пользователей
        self.history_analyzer = TenderHistoryAnalyzer()
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start"""
        # Безопасно получаем user_id и user_name
        user = getattr(update, 'effective_user', None)
        user_id = getattr(user, 'id', None)
        user_name = getattr(user, 'first_name', None) or "Пользователь"
        # Инициализируем сессию пользователя
        if user_id and user_id not in self.user_sessions:
            self.user_sessions[user_id] = {
                'status': 'waiting_for_tender',
                'state': BotState.MAIN_MENU,
                'tender_data': None,
                'files': None,
                'search_queries': None,
                'error_count': 0,
                'first_start': True,
                'history': []
            }
        elif user_id:
            self.user_sessions[user_id]['state'] = BotState.MAIN_MENU
            self.user_sessions[user_id]['error_count'] = 0
        # Безопасно получаем message
        message = safe_get_message(update)
        if message:
            await message.reply_text(
                "Привет! Я TenderBot – анализирую тендеры, проверяю компании и нахожу похожие закупки.\n\nВыберите нужный раздел или отправьте номер тендера / ИНН.",
                reply_markup=main_keyboard
            )
        else:
            chat = getattr(update, 'effective_chat', None)
            chat_id = getattr(chat, 'id', None)
            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Привет! Я TenderBot – анализирую тендеры, проверяю компании и нахожу похожие закупки.\n\nВыберите нужный раздел или отправьте номер тендера / ИНН.",
                    reply_markup=main_keyboard
                )
        logger.info(f"[bot] Пользователь {user_id} запустил бота")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help"""
        message = safe_get_message(update)
        if message:
            await message.reply_text(
                "Я TenderBot – анализирую тендеры, проверяю компании и нахожу похожие закупки.\n\nВыберите нужный раздел или отправьте номер тендера / ИНН.",
                reply_markup=main_keyboard
            )
        else:
            chat = getattr(update, 'effective_chat', None)
            chat_id = getattr(chat, 'id', None)
            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Я TenderBot – анализирую тендеры, проверяю компании и нахожу похожие закупки.\n\nВыберите нужный раздел или отправьте номер тендера / ИНН.",
                    reply_markup=main_keyboard
                )
    
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
        message = update.message
        if not message or not getattr(message, 'from_user', None) or not getattr(message, 'text', None):
            logger.warning("[bot] handle_message: message, from_user или text отсутствует")
            return
        user_id = message.from_user.id
        session = self.user_sessions.setdefault(user_id, {'state': BotState.MAIN_MENU})
        text = message.text.strip()
        logger.info(f"[bot] Получено сообщение от {user_id}: {text}, state={session['state']}")
        if session['state'] == BotState.ANALYZE:
            await analyze_handlers.analyze_tender_handler(update, context, self)
        elif session['state'] == BotState.SEARCH:
            await history_handlers.history_handler(update, context, self)
        elif session['state'] == BotState.SUPPLIER:
            await company_handlers.check_company_handler(update, context, self)
        else:
            await message.reply_text("Пожалуйста, выберите действие через меню.")
    
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
                
            formatted_data = tender_info  # или реализовать свою функцию форматирования, либо использовать format_tender_history если это история
            user_id = update.effective_user.id
            
            # Обновляем сессию пользователя
            if user_id in self.user_sessions:
                self.user_sessions[user_id]['tender_data'] = tender_info
                self.user_sessions[user_id]['formatted_info'] = formatted_data
                self.user_sessions[user_id]['status'] = 'ready_for_analysis'
            
            # Преобразуем словарь в строку для отображения
            formatted_info = f"""
📊 Статус: {formatted_data.get('status', 'Не указан')}
📋 Федеральный закон: {formatted_data.get('federal_law', 'Не указан')}-ФЗ
🏢 Заказчик: {formatted_data.get('customer', 'Не указан')}
📝 ИНН: {formatted_data.get('customer_inn', 'Не указан')}
📍 Адрес: {formatted_data.get('customer_address', 'Не указан')}
📄 Предмет поставки: {formatted_data.get('subject', 'Не указан')}
💰 Цена: {formatted_data.get('price', 'Не указана')}
📅 Дата публикации: {format_date(formatted_data.get('publication_date', 'Не указана'))}
⏰ Срок подачи до: {format_date(formatted_data.get('submission_deadline', 'Не указана'))}
📍 Место поставки: {formatted_data.get('delivery_place', 'Не указано')}
🏛️ ЭТП: {formatted_data.get('etp_name', 'Не указана')}
📞 Контакты: {formatted_data.get('contact_person', 'Не указано')} | {format_phone(formatted_data.get('contact_phone', 'Не указан'))}
📧 Email: {formatted_data.get('contact_email', 'Не указан')}
"""
            
            # Создаем клавиатуру с кнопками
            keyboard = [
                [InlineKeyboardButton("📄 Подробный анализ", callback_data="analyze")],
                [InlineKeyboardButton("📦 Позиции", callback_data="products_0")],
                [InlineKeyboardButton("📎 Документы", callback_data="documents_0")],
                [InlineKeyboardButton("📈 История тендеров", callback_data="history")],
                [InlineKeyboardButton("🔍 Найти поставщиков", callback_data="find_suppliers")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Разбиваем длинную информацию на части с более консервативным лимитом
            max_length = 3000  # Уменьшаем лимит для надежности
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
                try:
                    await update.message.reply_text(
                        f"📋 Информация о тендере (часть 1 из {len(parts)}):\n\n{parts[0]}",
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"[bot] Ошибка при отправке первой части: {e}")
                    # Пробуем отправить без форматирования
                    await update.message.reply_text(
                        f"📋 Информация о тендере (часть 1 из {len(parts)}):\n\n{parts[0]}",
                        reply_markup=reply_markup
                    )
                
                # Отправляем остальные части
                for i, part in enumerate(parts[1:], 2):
                    try:
                        await update.message.reply_text(
                            f"📋 Продолжение информации (часть {i} из {len(parts)}):\n\n{part}"
                        )
                    except Exception as e:
                        logger.error(f"[bot] Ошибка при отправке части {i}: {e}")
                        await update.message.reply_text(
                            f"📋 Продолжение информации (часть {i} из {len(parts)}):\n\n{part}"
                        )
            else:
                # Отправляем основную информацию одним сообщением
                try:
                    await update.message.reply_text(
                        f"📋 Информация о тендере\n\n{formatted_info}",
                        reply_markup=reply_markup
                    )
                except Exception as e:
                    logger.error(f"[bot] Ошибка при отправке основного сообщения: {e}")
                    # Пробуем отправить без форматирования
                    await update.message.reply_text(
                        f"📋 Информация о тендере\n\n{formatted_info}",
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
        # --- Показываем кнопки после анализа ---
        keyboard = [
            [InlineKeyboardButton("🔍 Найти поставщиков", callback_data="find_suppliers")],
            [InlineKeyboardButton("⚠️ Проверить риски", callback_data="check_risks")],
            [InlineKeyboardButton("📊 Показать похожие закупки", callback_data="history")]
        ]
        await bot.send_message(chat_id=chat_id, text="Что хотите сделать дальше?", reply_markup=InlineKeyboardMarkup(keyboard))
    
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
        user = getattr(query, 'from_user', None)
        user_id = getattr(user, 'id', None)
        await query.answer()
        data = query.data
        session = self.user_sessions.get(user_id, {})
        logger.info(f"[handle_callback] data={data}, user_id={user_id}, session={session}")
        # FSM: обновляем state в зависимости от действия
        if data == BACK_CB:
            session['state'] = BotState.MAIN_MENU
            await self._show_main_menu(query, context)
        elif data == "analyze_tender":
            session['state'] = BotState.ANALYZE
            await self._show_analyze_menu(query, context)
        elif data == "search_tenders":
            session['state'] = BotState.SEARCH
            await self._show_search_menu(query, context)
        elif data == "check_company":
            session['state'] = BotState.SUPPLIER
            await self._show_supplier_menu(query, context)
        elif data == "view_analytics":
            session['state'] = BotState.ANALYTICS
            await self._show_analytics_menu(query, context)
        elif data == "profile_menu":
            session['state'] = BotState.PROFILE
            await self._show_profile_menu(query, context)
        elif data == "help_menu":
            session['state'] = BotState.HELP
            await self._show_help_menu(query, context)
        elif data == "buy_subscription":
            session['state'] = BotState.LOCKED
            await self._show_locked_menu(query, context)
        else:
            await query.edit_message_text("Неизвестная команда.")

    async def _show_main_menu(self, query, context):
        try:
            await query.edit_message_text(welcome_text, reply_markup=main_keyboard)
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=welcome_text, reply_markup=main_keyboard)

    async def _show_analyze_menu(self, query, context):
        try:
            await query.edit_message_text(analyze_tender_text, reply_markup=analyze_keyboard)
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=analyze_tender_text, reply_markup=analyze_keyboard)

    async def _show_search_menu(self, query, context):
        try:
            await query.edit_message_text(search_tender_text, reply_markup=search_keyboard)
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=search_tender_text, reply_markup=search_keyboard)

    async def _show_supplier_menu(self, query, context):
        try:
            await query.edit_message_text(check_company_text, reply_markup=supplier_keyboard)
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=check_company_text, reply_markup=supplier_keyboard)

    async def _show_analytics_menu(self, query, context):
        try:
            await query.edit_message_text(analytics_text, reply_markup=analytics_keyboard)
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=analytics_text, reply_markup=analytics_keyboard)

    async def _show_profile_menu(self, query, context):
        try:
            await query.edit_message_text(profile_text, reply_markup=profile_keyboard)
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=profile_text, reply_markup=profile_keyboard)

    async def _show_help_menu(self, query, context):
        try:
            await query.edit_message_text(help_text, reply_markup=help_keyboard)
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=help_text, reply_markup=help_keyboard)

    async def _show_locked_menu(self, query, context):
        try:
            await query.edit_message_text(locked_text, reply_markup=locked_keyboard)
        except Exception:
            await context.bot.send_message(chat_id=query.message.chat_id, text=locked_text, reply_markup=locked_keyboard)

    async def _send_products_list_to_chat(self, bot, chat_id: int, tender_data: dict, page: int = 0, message_id: int = None) -> None:
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
        
        # Если передан message_id, редактируем существующее сообщение
        if message_id is not None:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=products_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        else:
            # Иначе отправляем новое сообщение
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
        self.app.add_handler(CommandHandler("cancel", self.cancel_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("cleanup", self.cleanup_command))
        self.app.add_handler(CommandHandler("check", lambda update, context: company_handlers.check_company_handler(update, context, self)))
        self.app.add_handler(CommandHandler("analyze", lambda update, context: analyze_handlers.analyze_tender_handler(update, context, self)))
        self.app.add_handler(CommandHandler("history", lambda update, context: history_handlers.history_handler(update, context, self)))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(CallbackQueryHandler(handle_tender_card_callback, pattern="^(download_docs|analyze_tz|check_customer|similar_history)$"))
        self.app.add_handler(CallbackQueryHandler(analyze_found_tender_callback, pattern=r"^analyze_found_tender:"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('products_page'), pattern=r"^products_page_"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('documents_page'), pattern=r"^documents_page_"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('download'), pattern=r"^download_"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('show_tenders'), pattern=r"^show_tenders$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('export_excel'), pattern=r"^export_excel$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('subscribe_selection'), pattern=r"^subscribe_selection$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('assess_reliability'), pattern=r"^assess_reliability$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('show_contacts'), pattern=r"^show_contacts$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('show_tender_history'), pattern=r"^show_tender_history$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('show_analytics'), pattern=r"^show_analytics$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('download_analytics_excel'), pattern=r"^download_analytics_excel$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('setup_notifications'), pattern=r"^setup_notifications$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('faq'), pattern=r"^faq$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('contact_support'), pattern=r"^contact_support$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('find_suppliers'), pattern=r"^find_suppliers$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('check_risks'), pattern=r"^check_risks$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('pay_from_balance'), pattern=r"^pay_from_balance$"))
        self.app.add_handler(CallbackQueryHandler(generic_callback_handler_factory('profile'), pattern=r"^profile$"))
    
    def run(self):
        try:
            # Настройка с увеличенными таймаутами
            builder = ApplicationBuilder().token(TELEGRAM_TOKEN)
            
            # Увеличиваем таймауты для предотвращения зависаний
            # Примечание: request_timeout, connect_timeout, read_timeout не поддерживаются в ApplicationBuilder
            # Вместо этого используем настройки в run_polling
            
            # Пробуем настроить прокси если есть проблемы с подключением
            try:
                # Проверяем, есть ли переменные окружения для прокси
                proxy_url = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY')
                if proxy_url:
                    logger.info(f"[bot] Используем прокси: {proxy_url}")
                    builder.proxy_url(proxy_url)
            except Exception as proxy_error:
                logger.warning(f"[bot] Не удалось настроить прокси: {proxy_error}")
            
            self.app = builder.build()
            
            # Дополнительные настройки для HTTP клиента
            if hasattr(self.app.bot, 'request'):
                self.app.bot.request.timeout = 60.0
            
            self.setup_handlers()
            logger.info("🚀 TenderBot запущен")
            print("🤖 TenderBot запущен и готов к работе!")
            print("📝 Логи сохраняются в файл:", LOG_FILE)
            
            # Запуск с оптимизированными настройками для уменьшения нагрузки
            self.app.run_polling(
                timeout=120,  # Увеличиваем интервал до 2 минут
                read_timeout=60,
                write_timeout=60,
                connect_timeout=30,
                pool_timeout=30,
                drop_pending_updates=True,  # Игнорируем старые обновления при запуске
                allowed_updates=['message', 'callback_query']  # Только нужные типы обновлений
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота: {e}")
            print(f"❌ Неожиданная ошибка: {e}")
            raise

    async def _generate_supplier_queries(self, formatted_info):
        # Пример: возвращаем список поисковых запросов на основе анализа
        # Можно сделать умнее, если в анализе есть ключевые слова
        subject = formatted_info.get('subject', '')
        return [subject] if subject else []

    async def _update_documents_message(self, bot, chat_id: int, message_id: int, tender_data: dict, reg_number: str, page: int) -> None:
        """Обновляет сообщение с документами"""
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
        
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=docs_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    async def _show_tenders_menu(self, query, context):
        """Показывает меню госзакупок"""
        message = """
📋 **Госзакупки**

Отправьте номер тендера (19-20 цифр) или ссылку на тендер с сайта госзакупок.

**Примеры:**
```
0123456789012345678
https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0123456789012345678
```

**Что я сделаю:**
• Получу данные о тендере через DaMIA API
• Скачаю документы (техзадание, условия)
• Проанализирую с помощью ИИ
• Предоставлю структурированный отчет
        """
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _show_supplier_check_menu(self, query, context):
        """Показывает меню проверки контрагентов"""
        message = """
🏢 **Проверка контрагентов**

Выберите тип проверки:

**📊 Доступные проверки:**
• 🏛️ **ФНС** - ЕГРЮЛ/ЕГРИП, признаки недобросовестности
• ⚖️ **Арбитраж** - Арбитражные дела и споры
• 📈 **Скоринг** - Оценка рисков и финансовое состояние
• 👮 **ФССП** - Исполнительные производства

**💡 Как использовать:**
1. Выберите тип проверки
2. Отправьте ИНН компании (10 или 12 цифр)
3. Получите подробный отчет

**Пример ИНН:** `7704627217`
        """
        
        keyboard = [
            [InlineKeyboardButton("🏛️ Проверка ФНС", callback_data="fns_check")],
            [InlineKeyboardButton("⚖️ Арбитражные дела", callback_data="arbitr_check")],
            [InlineKeyboardButton("📈 Скоринг", callback_data="scoring_check")],
            [InlineKeyboardButton("👮 Проверка ФССП", callback_data="fssp_check")],
            [InlineKeyboardButton("🔙 Главное меню", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _show_supplier_search_menu(self, query, context):
        """Показывает меню поиска поставщиков"""
        message = """
🔎 **Поиск поставщиков**

Отправьте название товара или услуги для поиска поставщиков.

**Что я найду:**
• Контакты поставщиков
• Коммерческие предложения
• Цены и условия
• Рейтинг поставщиков

**Примеры запросов:**
```
металлопрокат
строительные материалы
канцелярские товары
```
        """
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _show_profile_menu(self, query, context):
        """Показывает личный кабинет"""
        user_id = query.from_user.id
        session = self.user_sessions.get(user_id, {})
        
        # Получаем информацию о пользователе
        user_info = await self._get_user_info(user_id)
        
        message = f"""
👤 **Личный кабинет**

📋 **Информация об аккаунте**
🆔 **User ID:** `{user_id}`
🥇 **Полный доступ:** {'✅ Да' if user_info['has_subscription'] else '❌ Нет'}
📅 **Подписка истекает:** {user_info['subscription_expires']}
💰 **Баланс:** {user_info['balance']} руб.
💳 **Реф. баланс:** {user_info['ref_balance']} руб.
🛍️ **Покупок:** {user_info['purchases_count']} на {user_info['purchases_amount']} руб.
🔍 **Запросов:** {user_info['requests_count']} / {user_info['daily_limit']}
🆓 **Дневной лимит:** {user_info['daily_limit']} запросов

**Статистика использования:**
• Проверено тендеров: {len([s for s in self.user_sessions.values() if s.get('status') == 'completed'])}
• Проверено контрагентов: {user_info['suppliers_checked']}
• Текущий статус: {session.get('status', 'не активен')}
        """
        
        # Определяем кнопки в зависимости от статуса подписки
        if user_info['has_subscription']:
            subscription_button = InlineKeyboardButton("🔄 Продлить подписку", callback_data="extend_subscription")
        else:
            subscription_button = InlineKeyboardButton("💳 Купить подписку", callback_data="buy_subscription")
        
        keyboard = [
            [subscription_button],
            [InlineKeyboardButton("👥 Реферальная система", callback_data="referral_system")],
            [InlineKeyboardButton("❓ Помощь", callback_data="help")]
        ]
        
        # Добавляем кнопку админ панели для пользователя hoproqr
        if query.from_user.username == "hoproqr":
            keyboard.append([InlineKeyboardButton("⚙️ Админ панель", callback_data="admin_panel")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _handle_fns_check(self, query, context):
        """Обработчик проверки ФНС"""
        message = """
🏛️ **Проверка ФНС**

Отправьте ИНН компании для проверки:

**Что проверяется:**
• Данные ЕГРЮЛ/ЕГРИП
• Признаки недобросовестности
• Массовые директора/учредители
• Ликвидация и реорганизация
• Нарушения и штрафы

**Пример:** `7704627217`
        """
        
        keyboard = [
            [InlineKeyboardButton("🔙 К проверке контрагентов", callback_data="back_to_supplier_check")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Устанавливаем статус ожидания ИНН для ФНС
        user_id = query.from_user.id
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {}
        self.user_sessions[user_id]['status'] = 'waiting_for_inn_fns'
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _handle_arbitr_check(self, query, context):
        """Обработчик проверки арбитража"""
        message = """
⚖️ **Арбитражные дела**

Отправьте ИНН компании для проверки:

**Что проверяется:**
• Арбитражные дела
• Роли в делах (истец/ответчик)
• Суммы исков
• Статусы дел
• История арбитражных споров

**Пример:** `7704627217`
        """
        
        keyboard = [
            [InlineKeyboardButton("🔙 К проверке контрагентов", callback_data="back_to_supplier_check")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Устанавливаем статус ожидания ИНН для арбитража
        user_id = query.from_user.id
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {}
        self.user_sessions[user_id]['status'] = 'waiting_for_inn_arbitr'
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _handle_scoring_check(self, query, context):
        """Обработчик скоринга"""
        message = """
📈 **Скоринг проверка**

Отправьте ИНН компании для скоринга:

**Доступные модели:**
• Банкроты (2016)
• Черный список 115-ФЗ
• Дисквалифицированные лица
• Проблемные кредиты
• Антиотмывочное законодательство

**Пример:** `7704627217`
        """
        
        keyboard = [
            [InlineKeyboardButton("🔙 К проверке контрагентов", callback_data="back_to_supplier_check")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Устанавливаем статус ожидания ИНН для скоринга
        user_id = query.from_user.id
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {}
        self.user_sessions[user_id]['status'] = 'waiting_for_inn_scoring'
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _handle_fssp_check(self, query, context):
        """Обработчик проверки ФССП"""
        message = """
👮 **Проверка ФССП**

Отправьте ИНН компании для проверки:

**Что проверяется:**
• Исполнительные производства
• Задолженности
• Активные дела
• История производств

**Пример:** `7704627217`
        """
        
        keyboard = [
            [InlineKeyboardButton("🔙 К проверке контрагентов", callback_data="back_to_supplier_check")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Устанавливаем статус ожидания ИНН для ФССП
        user_id = query.from_user.id
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {}
        self.user_sessions[user_id]['status'] = 'waiting_for_inn_fssp'
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def _handle_inn_input(self, update, context, message_text, check_type):
        """Обработка ввода ИНН для проверки контрагентов"""
        user_id = update.effective_user.id
        
        # Проверяем, что введен корректный ИНН (10 или 12 цифр)
        inn = message_text.strip()
        if not inn.isdigit() or len(inn) not in [10, 12]:
            await update.message.reply_text(
                "❌ Неверный формат ИНН!\n\n"
                "ИНН должен содержать:\n"
                "• 10 цифр для юридических лиц\n"
                "• 12 цифр для физических лиц\n\n"
                "Пример: `7704627217`",
                parse_mode='Markdown'
            )
            return
        
        # Отправляем сообщение о начале проверки
        check_message = await update.message.reply_text(f"🔍 Проверяю ИНН {inn}...")
        
        try:
            result = None
            
            if check_type == 'fns':
                result = await self._check_fns(inn)
            elif check_type == 'arbitr':
                result = await self._check_arbitr(inn)
            elif check_type == 'scoring':
                result = await self._check_scoring(inn)
            elif check_type == 'fssp':
                result = await self._check_fssp(inn)
            
            # Удаляем промежуточное сообщение
            await check_message.delete()
            
            if result:
                # Создаем клавиатуру с кнопками навигации
                keyboard = [
                    [InlineKeyboardButton("🔍 Проверить другой ИНН", callback_data=f"{check_type}_check")],
                    [InlineKeyboardButton("🏢 К проверке контрагентов", callback_data="back_to_supplier_check")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(result, parse_mode='Markdown', reply_markup=reply_markup)
            else:
                await update.message.reply_text("❌ Ошибка при проверке. Попробуйте позже.")
                
        except Exception as e:
            # Удаляем промежуточное сообщение при ошибке
            await check_message.delete()
            
            logger.error(f"[bot] Ошибка при проверке ИНН {inn}: {e}")
            # Экранируем специальные символы для Markdown
            error_msg = str(e).replace('*', '\\*').replace('_', '\\_').replace('`', '\\`').replace('[', '\\[').replace(']', '\\]')
            
            # Создаем клавиатуру с кнопками навигации
            keyboard = [
                [InlineKeyboardButton("🔍 Попробовать снова", callback_data=f"{check_type}_check")],
                [InlineKeyboardButton("🏢 К проверке контрагентов", callback_data="back_to_supplier_check")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"❌ Произошла ошибка при проверке: {error_msg}",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        
        # Сбрасываем статус пользователя
        self.user_sessions[user_id]['status'] = 'waiting_for_tender'
    
    async def _check_fns(self, inn: str) -> str:
        """Проверка по базам ФНС"""
        try:
            # Получаем данные компании
            company_data = await fns_api.get_company_info(inn)
            check_data = await fns_api.check_company(inn)
            
            result = f"🏢 **Проверка ФНС для ИНН {inn}**\n\n"
            
            # Форматируем данные компании
            company_info = fns_api.format_company_info(company_data)
            result += company_info + "\n\n"
            
            # Форматируем результаты проверки
            check_info = fns_api.format_company_check(check_data)
            result += check_info
            
            return result
            
        except Exception as e:
            logger.error(f"[bot] Ошибка при проверке ФНС: {e}")
            return f"❌ Ошибка при проверке ФНС: {str(e)}"
    
    async def _check_arbitr(self, inn: str) -> str:
        """Проверка арбитражных дел"""
        try:
            # Получаем арбитражные дела
            cases_data = await arbitr_api.get_arbitrage_cases_by_inn(inn)
            
            result = f"⚖️ **Проверка арбитражных дел для ИНН {inn}**\n\n"
            
            if cases_data.get('status') == 'found':
                # Всегда используем форматированный вывод
                summary = arbitr_api.format_arbitrage_summary(cases_data)
                result += summary
            elif cases_data.get('status') == 'not_found':
                result += "✅ **Арбитражные дела не найдены**\n\n"
                result += "💡 *Это означает, что компания не участвовала в арбитражных спорах, что является положительным фактором.*"
            elif cases_data.get('status') == 'error':
                error_msg = cases_data.get('error', 'Неизвестная ошибка')
                result += f"❌ **Ошибка при получении данных:** {error_msg}"
            else:
                result += "❌ **Не удалось получить данные об арбитражных делах**"
            
            return result
        except Exception as e:
            logger.error(f"[bot] Ошибка при проверке арбитражей: {e}")
            return f"❌ **Ошибка при проверке арбитражей:** {str(e)}"
    
    async def _check_scoring(self, inn: str) -> str:
        """Проверка скоринга"""
        try:
            # Получаем скоринг по всем моделям и фин. коэффициенты
            scoring_data = await scoring_api.get_comprehensive_scoring(inn)
            result = f"📊 **Скоринг для ИНН {inn}**\n\n"
            
            if scoring_data.get('status') == 'completed':
                results = scoring_data.get('results', {})
                
                # Словарь для перевода названий моделей на русский
                model_names = {
                    '_bankrots2016': 'Риск банкротства (2016)',
                    '_tech': 'Технический скоринг',
                    '_diskf': 'Дискриминантный анализ',
                    '_problemCredit': 'Проблемные кредиты',
                    '_zsk': 'Защита от кредитных рисков',
                    'financial_coefficients': 'Финансовые коэффициенты'
                }
                
                # Модели скоринга
                result += "🎯 **Результаты скоринга:**\n"
                scoring_models = []
                for model_name, model_result in results.items():
                    if model_name == 'financial_coefficients':
                        continue
                    if model_result.get('status') == 'success':
                        score = model_result.get('score', 0)
                        risk_level = model_result.get('risk_level', 'unknown')
                        probability = model_result.get('probability', 0)
                        
                        # Получаем русское название модели
                        display_name = model_names.get(model_name, model_name)
                        safe_model_name = escape_markdown(str(display_name))
                        safe_risk_level = escape_markdown(str(risk_level))
                        
                        # Определяем эмодзи для уровня риска
                        risk_emoji = "🟢" if risk_level == "low" else "🟡" if risk_level == "medium" else "🔴" if risk_level == "high" else "⚪"
                        
                        if isinstance(probability, (int, float)):
                            result += f"• {risk_emoji} **{safe_model_name}:** {score} ({safe_risk_level}, {probability:.1f}%)\n"
                        else:
                            result += f"• {risk_emoji} **{safe_model_name}:** {score} ({safe_risk_level}, {probability})\n"
                    else:
                        # Получаем русское название модели
                        display_name = model_names.get(model_name, model_name)
                        safe_model_name = escape_markdown(str(display_name))
                        result += f"• ⚪ **{safe_model_name}:** Ошибка\n"
                
                # Финансовые коэффициенты
                fin_data = results.get('financial_coefficients', {})
                if fin_data.get('status') == 'found':
                    result += "\n💰 **Ключевые финансовые показатели:**\n"
                    coefs = fin_data.get('coefficients', {})
                    
                    # Определяем ключевые коэффициенты с их названиями и типами
                    key_coefs = {
                        'КоэфТекЛикв': {'name': 'Текущая ликвидность', 'type': 'ratio', 'unit': ''},
                        'РентАктивов': {'name': 'Рентабельность активов', 'type': 'percent', 'unit': '%'},
                        'КоэфФинАвт': {'name': 'Финансовая автономия', 'type': 'ratio', 'unit': ''},
                        'РентПродаж': {'name': 'Рентабельность продаж', 'type': 'percent', 'unit': '%'}
                    }
                    
                    for coef_code, coef_info in key_coefs.items():
                        value = coefs.get(coef_code)
                        if value is not None:
                            safe_coef_name = escape_markdown(str(coef_info['name']))
                            
                            if isinstance(value, dict):
                                years = sorted(value.keys(), reverse=True)
                                if years:
                                    latest_year = years[0]
                                    year_data = value[latest_year]
                                    
                                    if isinstance(year_data, dict) and 'Знач' in year_data:
                                        display_value = year_data['Знач']
                                        norm_value = year_data.get('Норма')
                                        norm_low = year_data.get('НормаНижн')
                                        norm_high = year_data.get('НормаВерхн')
                                        norm_comparison = year_data.get('НормаСравн', 'нет данных')
                                        
                                        # Форматируем значение
                                        if isinstance(display_value, (int, float)):
                                            if coef_info['type'] == 'percent':
                                                display_value_str = f"{display_value:.3f}{coef_info['unit']}"
                                            else:
                                                display_value_str = f"{display_value:.3f}{coef_info['unit']}"
                                        else:
                                            display_value_str = f"{display_value}{coef_info['unit']}"
                                        
                                        # Форматируем нормы
                                        if norm_value is not None and isinstance(norm_value, (int, float)):
                                            norm_value_str = f"{norm_value:.3f}{coef_info['unit']}"
                                        else:
                                            norm_value_str = "нет данных"
                                            
                                        if norm_low is not None and norm_high is not None and isinstance(norm_low, (int, float)) and isinstance(norm_high, (int, float)):
                                            norm_range_str = f"{norm_low:.3f}-{norm_high:.3f}{coef_info['unit']}"
                                        else:
                                            norm_range_str = "нет данных"
                                        
                                        # Определяем эмодзи для сравнения с нормой
                                        comparison_emoji = "✅" if "выше нормы" in norm_comparison.lower() else "⚠️" if "ниже нормы" in norm_comparison.lower() else "🟢" if "в пределах нормы" in norm_comparison.lower() else "⚪"
                                        
                                        result += f"• {comparison_emoji} **{safe_coef_name} ({latest_year}):** {display_value_str}\n"
                                        result += f"  └ Норма: {norm_value_str} (диапазон: {norm_range_str})\n"
                                        result += f"  └ Оценка: {norm_comparison}\n"
                            elif isinstance(value, (int, float)):
                                result += f"• ⚪ **{safe_coef_name}:** {value:.3f}{coef_info['unit']}\n"
                            else:
                                result += f"• ⚪ **{safe_coef_name}:** {value}\n"
                else:
                    result += "\n❌ **Финансовые показатели недоступны**\n"
            else:
                result += "❌ **Не удалось получить скоринг или финансовые показатели.**\n"
            
            return result
        except Exception as e:
            logger.error(f"[bot] Ошибка при проверке скоринга: {e}")
            return f"❌ **Ошибка при проверке скоринга:** {str(e)}"
    
    async def _check_fssp(self, inn: str) -> str:
        """Проверка ФССП"""
        try:
            # Получаем данные ФССП
            fssp_data = await fssp_client.check_company(inn)
            
            # Если нет производств и нет данных о компании — выводим короткое сообщение
            if (
                fssp_data and fssp_data.get('status') == 'success' and
                (not fssp_data.get('executive_proceedings') or len(fssp_data.get('executive_proceedings', [])) == 0) and
                (not fssp_data.get('company_info') or all(
                    not fssp_data['company_info'].get(k) or fssp_data['company_info'].get(k) == 'Не указано'
                    for k in ['name', 'inn', 'ogrn', 'address']
                ))
            ):
                return f"👮 **Проверка ФССП для ИНН {inn}**\n\n✅ **Компания не найдена в базе ФССП или у нее нет исполнительных производств.**\n\n💡 *Это означает, что у компании нет задолженностей по исполнительным производствам, что является положительным фактором.*"
            
            result = f"👮 **Проверка ФССП для ИНН {inn}**\n\n"
            
            if fssp_data and fssp_data.get('status') == 'success':
                company_info = fssp_data.get('company_info', {})
                proceedings = fssp_data.get('executive_proceedings', [])
                summary = fssp_data.get('summary', {})
                
                # Информация о компании
                if company_info:
                    safe_name = escape_markdown(str(company_info.get('name', 'Не указано')))
                    safe_inn = escape_markdown(str(company_info.get('inn', 'Не указано')))
                    safe_ogrn = escape_markdown(str(company_info.get('ogrn', 'Не указано')))
                    safe_address = escape_markdown(str(company_info.get('address', 'Не указано')))
                    
                    # Проверяем, есть ли примечание о недоступности данных
                    note = company_info.get('note')
                    if note:
                        result += f"ℹ️ **{note}**\n\n"
                    else:
                        result += f"🏢 **Компания:** {safe_name}\n"
                        result += f"**ИНН:** {safe_inn}\n"
                        result += f"**ОГРН:** {safe_ogrn}\n"
                        result += f"**Адрес:** {safe_address}\n\n"
                
                # Сводка по производствам
                total_proceedings = summary.get('total_proceedings', 0)
                active_proceedings = summary.get('active_proceedings', 0)
                total_debt = summary.get('total_debt', 0)
                
                result += f"📋 **Исполнительные производства:**\n"
                result += f"• Всего: {total_proceedings}\n"
                result += f"• Активных: {active_proceedings}\n"
                # Проверяем, что total_debt - это число
                if isinstance(total_debt, (int, float)):
                    result += f"• Общая задолженность: {total_debt:,.2f} руб.\n\n"
                else:
                    result += f"• Общая задолженность: {total_debt} руб.\n\n"
                
                if proceedings:
                    result += "📄 **Последние производства:**\n"
                    for i, proc in enumerate(proceedings[:5], 1):
                        number = proc.get('number', 'Не указано')
                        amount = proc.get('amount', 0)
                        status = proc.get('status', 'Не указано')
                        # Проверяем, что amount - это число
                        if isinstance(amount, (int, float)):
                            result += f"{i}. {number} - {amount:,.2f} руб. ({status})\n"
                        else:
                            result += f"{i}. {number} - {amount} руб. ({status})\n"
                else:
                    result += "✅ **Исполнительные производства не найдены**\n"
            else:
                error_msg = fssp_data.get('error', 'Неизвестная ошибка') if fssp_data else 'Данные недоступны'
                result += f"❌ **Данные ФССП недоступны: {error_msg}**\n"
            
            return result
            
        except Exception as e:
            logger.error(f"[bot] Ошибка при проверке ФССП: {e}")
            return f"❌ Ошибка при проверке ФССП: {str(e)}"

    async def _get_user_info(self, user_id: int) -> dict:
        """Получает информацию о пользователе"""
        # В реальном проекте здесь была бы база данных
        # Пока используем заглушку с базовой логикой
        
        # Получаем статистику из сессий
        completed_tenders = len([s for s in self.user_sessions.values() if s.get('status') == 'completed'])
        
        # Заглушка для демонстрации
        user_info = {
            'has_subscription': False,  # По умолчанию без подписки
            'subscription_expires': 'Не активна',
            'balance': 0,
            'ref_balance': 0,
            'purchases_count': 0,
            'purchases_amount': 0,
            'requests_count': completed_tenders * 3,  # Примерно 3 запроса на тендер
            'daily_limit': 100,
            'suppliers_checked': completed_tenders * 2  # Примерно 2 проверки контрагента на тендер
        }
        
        # Проверяем, есть ли у пользователя активная подписка
        # В реальном проекте это проверялось бы в базе данных
        if user_id % 3 == 0:  # Каждый третий пользователь имеет подписку для демонстрации
            user_info.update({
                'has_subscription': True,
                'subscription_expires': '2024-12-31',
                'balance': 1500,
                'ref_balance': 250,
                'purchases_count': 3,
                'purchases_amount': 4500
            })
        
        return user_info
    
    async def _show_buy_subscription(self, query, context):
        """Показывает страницу покупки подписки"""
        message = """
💳 **Покупка подписки**

**Доступные тарифы:**

🥉 **Базовый** - 999 руб/месяц
• 100 запросов в день
• Проверка контрагентов
• Анализ тендеров
• Базовая поддержка

🥈 **Стандарт** - 1999 руб/месяц
• 300 запросов в день
• Все функции базового
• Приоритетная поддержка
• Экспорт отчетов

🥇 **Премиум** - 3999 руб/месяц
• Безлимитные запросы
• Все функции стандарта
• Персональный менеджер
• API доступ
• Белый лейбл

**Для покупки свяжитесь с менеджером:**
📧 support@tenderbot.ru
📱 +7 (999) 123-45-67
        """
        
        keyboard = [
            [InlineKeyboardButton("📧 Написать в поддержку", callback_data="contact_support")],
            [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _show_extend_subscription(self, query, context):
        """Показывает страницу продления подписки"""
        user_id = query.from_user.id
        user_info = await self._get_user_info(user_id)
        
        message = f"""
🔄 **Продление подписки**

**Текущая подписка:**
📅 Истекает: {user_info['subscription_expires']}
💰 Баланс: {user_info['balance']} руб.

**Варианты продления:**

🥉 **Базовый** - 999 руб/месяц
🥈 **Стандарт** - 1999 руб/месяц  
🥇 **Премиум** - 3999 руб/месяц

**Для продления:**
📧 support@tenderbot.ru
📱 +7 (999) 123-45-67

**Или используйте баланс аккаунта**
        """
        
        keyboard = [
            [InlineKeyboardButton("💳 Оплатить с баланса", callback_data="pay_from_balance")],
            [InlineKeyboardButton("📧 Написать в поддержку", callback_data="contact_support")],
            [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _show_referral_system(self, query, context):
        """Показывает реферальную систему"""
        user_id = query.from_user.id
        user_info = await self._get_user_info(user_id)
        
        # Генерируем реферальную ссылку
        ref_link = f"https://t.me/TenderBot?start=ref{user_id}"
        
        message = f"""
👥 **Реферальная система**

**Ваша реферальная ссылка:**
`{ref_link}`

**Как это работает:**
• Пригласите друзей по ссылке
• За каждого приглашенного получаете 100 руб.
• Приглашенный получает 50 руб. на баланс
• Реферальные средства можно тратить на подписку

**Ваша статистика:**
💳 Реферальный баланс: {user_info['ref_balance']} руб.
👥 Приглашено пользователей: {user_info['ref_balance'] // 100}
🎁 Заработано всего: {user_info['ref_balance']} руб.

**Условия:**
• Реферал должен зарегистрироваться по вашей ссылке
• Реферал должен совершить первую покупку
• Бонусы начисляются в течение 24 часов
        """
        
        keyboard = [
            [InlineKeyboardButton("📤 Поделиться ссылкой", callback_data="share_ref_link")],
            [InlineKeyboardButton("📊 Статистика рефералов", callback_data="ref_statistics")],
            [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def _show_contact_support(self, query, context):
        """Показывает страницу контакта с поддержкой"""
        message = """
📧 **Контакты поддержки**

Если у вас возникли вопросы или проблемы, пожалуйста, свяжитесь с нами:
📧 support@tenderbot.ru
📱 +7 (999) 123-45-67
        """
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def _show_pay_from_balance(self, query, context):
        """Показывает страницу оплаты с баланса"""
        message = """
💳 **Оплата с баланса**

Вы можете оплатить подписку с вашего баланса. Пожалуйста, введите сумму для оплаты:
        """
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="extend_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def _share_ref_link(self, query, context):
        """Показывает страницу деления ссылки"""
        user_id = query.from_user.id
        user_info = await self._get_user_info(user_id)
        ref_link = f"https://t.me/TenderBot?start=ref{user_id}"
        
        message = f"""
📤 **Поделиться ссылкой**

Вы можете поделиться своей реферальной ссылкой с друзьями:
`{ref_link}`

**Как это работает:**
• Пригласите друзей по ссылке
• За каждого приглашенного получаете 100 руб.
• Приглашенный получает 50 руб. на баланс
• Реферальные средства можно тратить на подписку

**Ваша статистика:**
💳 Реферальный баланс: {user_info['ref_balance']} руб.
👥 Приглашено пользователей: {user_info['ref_balance'] // 100}
🎁 Заработано всего: {user_info['ref_balance']} руб.

**Условия:**
• Реферал должен зарегистрироваться по вашей ссылке
• Реферал должен совершить первую покупку
• Бонусы начисляются в течение 24 часов
        """
        
        keyboard = [
            [InlineKeyboardButton("📤 Поделиться ссылкой", callback_data="share_ref_link")],
            [InlineKeyboardButton("📊 Статистика рефералов", callback_data="ref_statistics")],
            [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def _show_ref_statistics(self, query, context):
        """Показывает статистику рефералов"""
        user_id = query.from_user.id
        user_info = await self._get_user_info(user_id)
        ref_count = user_info['ref_balance'] // 100
        
        message = f"""
📊 **Статистика рефералов**

👥 Приглашено пользователей: {ref_count}
🎁 Заработано всего: {user_info['ref_balance']} руб.

**Условия:**
• Реферал должен зарегистрироваться по вашей ссылке
• Реферал должен совершить первую покупку
• Бонусы начисляются в течение 24 часов
        """
        
        keyboard = [
            [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def _show_admin_panel(self, query, context):
        """Показывает панель администратора"""
        message = """
👨‍💼 **Панель администратора**

Выберите нужный раздел:
        """
        
        keyboard = [
            [InlineKeyboardButton("👥 Пользователи", callback_data="admin_users")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_statistics")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
            [InlineKeyboardButton("📋 Логи", callback_data="admin_logs")],
            [InlineKeyboardButton("🔙 Назад", callback_data="profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def _show_admin_users(self, query, context):
        """Показывает список пользователей"""
        # Получаем статистику пользователей
        total_users = len(self.user_sessions)
        active_users = len([s for s in self.user_sessions.values() if s.get('status') != 'waiting_for_tender'])
        completed_analyses = len([s for s in self.user_sessions.values() if s.get('status') == 'completed'])
        
        message = f"""
👥 **Управление пользователями**

📊 **Общая статистика:**
• Всего пользователей: {total_users}
• Активных пользователей: {active_users}
• Завершенных анализов: {completed_analyses}

**Последние активные пользователи:**
        """
        
        # Показываем последние 5 активных пользователей
        recent_users = []
        for user_id, session in list(self.user_sessions.items())[-5:]:
            if session.get('status') != 'waiting_for_tender':
                recent_users.append(f"• ID: {user_id} - {session.get('status', 'неизвестно')}")
        
        if recent_users:
            message += "\n".join(recent_users)
        else:
            message += "\n• Нет активных пользователей"
        
        keyboard = [
            [InlineKeyboardButton("📊 Подробная статистика", callback_data="admin_users_detailed")],
            [InlineKeyboardButton("🔍 Поиск пользователя", callback_data="admin_search_user")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def _show_admin_statistics(self, query, context):
        """Показывает статистику пользователей"""
        # Подсчитываем статистику
        total_users = len(self.user_sessions)
        completed_analyses = len([s for s in self.user_sessions.values() if s.get('status') == 'completed'])
        ready_analyses = len([s for s in self.user_sessions.values() if s.get('status') == 'ready_for_analysis'])
        tender_found = len([s for s in self.user_sessions.values() if s.get('status') == 'tender_found'])
        
        # Подсчитываем общую статистику запросов
        total_requests = sum(len([s for s in self.user_sessions.values() if s.get('status') == 'completed']) * 3, 0)
        
        message = f"""
📊 **Статистика системы**

👥 **Пользователи:**
• Всего пользователей: {total_users}
• Завершенных анализов: {completed_analyses}
• Готовых к анализу: {ready_analyses}
• Найденных тендеров: {tender_found}

🔍 **Запросы:**
• Общее количество запросов: {total_requests}
• Среднее на пользователя: {total_requests // max(total_users, 1)}

📈 **Активность:**
• Активных сессий: {len([s for s in self.user_sessions.values() if s.get('status') != 'waiting_for_tender'])}
• Ожидающих ввода: {len([s for s in self.user_sessions.values() if s.get('status') == 'waiting_for_tender'])}

**Периоды:**
• Сегодня: {len([s for s in self.user_sessions.values() if s.get('status') == 'completed'])} анализов
• За неделю: {completed_analyses} анализов
• За месяц: {completed_analyses} анализов
        """
        
        keyboard = [
            [InlineKeyboardButton("📅 По дням", callback_data="admin_stats_daily")],
            [InlineKeyboardButton("📊 По функциям", callback_data="admin_stats_functions")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def _show_admin_settings(self, query, context):
        """Показывает настройки"""
        message = """
⚙️ **Настройки системы**

**Текущие параметры:**
• Дневной лимит запросов: 100
• Максимальный размер файла: 50MB
• Время жизни кэша: 1 час
• Максимальные попытки API: 3

**API статус:**
• DaMIA API: ✅ Активен
• OpenAI API: ✅ Активен
• SerpAPI: ✅ Активен
• FNS API: ✅ Активен
• Arbitr API: ✅ Активен
• Scoring API: ✅ Активен
• FSSP API: ✅ Активен

**Системные параметры:**
• Логирование: ✅ Включено
• VPN для OpenAI: ✅ Настроен
• Автоочистка файлов: ✅ Включена
        """
        
        keyboard = [
            [InlineKeyboardButton("🔧 Изменить лимиты", callback_data="admin_change_limits")],
            [InlineKeyboardButton("🔄 Перезапустить API", callback_data="admin_restart_api")],
            [InlineKeyboardButton("🧹 Очистить кэш", callback_data="admin_clear_cache")],
            [InlineKeyboardButton("📋 Системные логи", callback_data="admin_system_logs")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def _show_admin_logs(self, query, context):
        """Показывает логи"""
        # Получаем последние записи из логов
        log_file = "bot_output.log"
        recent_logs = []
        
        try:
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    recent_logs = lines[-10:]  # Последние 10 строк
        except Exception as e:
            recent_logs = [f"Ошибка чтения логов: {e}"]
        
        message = """
📋 **Системные логи**

**Последние записи:**
        """
        
        if recent_logs:
            for log in recent_logs[-5:]:  # Показываем последние 5
                # Очищаем длинные строки
                clean_log = log.strip()[:100] + "..." if len(log) > 100 else log.strip()
                message += f"\n• {clean_log}"
        else:
            message += "\n• Логи не найдены"
        
        message += """

**Типы логов:**
• INFO - Информационные сообщения
• WARNING - Предупреждения
• ERROR - Ошибки
• DEBUG - Отладочная информация
        """
        
        keyboard = [
            [InlineKeyboardButton("📄 Полные логи", callback_data="admin_full_logs")],
            [InlineKeyboardButton("🔍 Поиск по логам", callback_data="admin_search_logs")],
            [InlineKeyboardButton("🧹 Очистить логи", callback_data="admin_clear_logs")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

    async def _show_admin_users_detailed(self, query, context):
        # Добавьте реализацию для подробной статистики пользователей
        pass

    async def _show_admin_search_user(self, query, context):
        # Добавьте реализацию для поиска пользователя
        pass

    async def _show_admin_stats_daily(self, query, context):
        # Добавьте реализацию для ежедневных статистических данных
        pass

    async def _show_admin_stats_functions(self, query, context):
        # Добавьте реализацию для статистики функций
        pass

    async def _show_admin_change_limits(self, query, context):
        # Добавьте реализацию для изменения лимитов
        pass

    async def _show_admin_restart_api(self, query, context):
        # Добавьте реализацию для перезапуска API
        pass

    async def _show_admin_clear_cache(self, query, context):
        # Добавьте реализацию для очистки кэша
        pass

    async def _show_admin_system_logs(self, query, context):
        # Добавьте реализацию для системных логов
        pass

    async def _show_admin_full_logs(self, query, context):
        # Добавьте реализацию для полных логов
        pass

    async def _show_admin_search_logs(self, query, context):
        # Добавьте реализацию для поиска логов
        pass

    async def _show_admin_clear_logs(self, query, context):
        # Добавьте реализацию для очистки логов
        pass

    async def _show_company_profile(self, query, context):
        """Показать агрегированный профиль компании по ИНН"""
        user_id = query.from_user.id
        valid, session = validate_user_session(user_id, self.user_sessions, ['ready_for_analysis', 'completed'])
        if not valid:
            await handle_session_error(query)
            return
        inn = session.get('inn')
        if not inn:
            await query.edit_message_text("❌ Не удалось определить ИНН компании.")
            return
        await query.edit_message_text("🔍 Формируем профиль компании...")
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            profile_text = await loop.run_in_executor(None, build_company_profile, inn)
            await context.bot.send_message(chat_id=query.message.chat_id, text=profile_text, parse_mode='HTML')
        except Exception as e:
            logger.error(f"[bot] Ошибка при формировании профиля компании: {e}")
            await query.edit_message_text(f"❌ Ошибка при формировании профиля компании: {str(e)}")

    async def _find_suppliers_exportbase(self, inn: str) -> str:
        """Поиск поставщиков через ExportBase по ИНН"""
        try:
            company = get_company_by_inn(inn)
            if not company:
                return "❌ Компания не найдена в ExportBase."
            name = company.get('legal_name', '—')
            phone = company.get('stationary_phone', '') or company.get('mobile_phone', '')
            email = company.get('email', '')
            site = company.get('site', '')
            result = f"🏢 <b>{name}</b>\nИНН: <code>{inn}</code>\n"
            if phone:
                result += f"📞 Телефон: {phone}\n"
            if email:
                result += f"✉️ Email: {email}\n"
            if site:
                result += f"🌐 Сайт: {site}\n"
            return result
        except Exception as e:
            return f"❌ Ошибка поиска поставщика: {e}"

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Сброс FSM и возврат в главное меню"""
        user = getattr(update, 'effective_user', None)
        user_id = getattr(user, 'id', None)
        if user_id in self.user_sessions:
            self.user_sessions[user_id]['state'] = BotState.MAIN_MENU
            self.user_sessions[user_id]['status'] = 'waiting_for_tender'
        message = safe_get_message(update)
        if message:
            await message.reply_text(
                "Привет! Я TenderBot – анализирую тендеры, проверяю компании и нахожу похожие закупки.\n\nВыберите нужный раздел или отправьте номер тендера / ИНН.",
                reply_markup=main_keyboard
            )

def generic_callback_handler_factory(pattern_name):
    async def handler(update, context):
        logger = logging.getLogger(__name__)
        query = update.callback_query
        logger.info(f"[generic_callback_handler] pattern={pattern_name}, data={getattr(query, 'data', None)}, user_id={getattr(getattr(query, 'from_user', None), 'id', None)}")
        await query.answer()
        await query.edit_message_text(f"⚙️ Функция '{pattern_name}' в разработке.")
    return handler

# Создаем и запускаем бота
if __name__ == "__main__":
    bot = TenderBot()
    bot.run()