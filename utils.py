"""
Утилиты для TenderBot
"""
import logging
import functools
import time
import json
import hashlib
import os
from typing import Optional, Dict, Any, Callable
from telegram import Update

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
                        import asyncio
                        await asyncio.sleep(delay * (2 ** attempt))  # Экспоненциальная задержка
            logger.error(f"[retry] Все попытки исчерпаны: {last_exception}")
            raise last_exception
        return wrapper
    return decorator

def get_cache_key(tender_data: Dict, files: list) -> str:
    """Генерирует ключ кэша для анализа"""
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

def format_file_size(size_bytes: int) -> str:
    """Форматирует размер файла в читаемый вид"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f}{size_names[i]}"

def sanitize_filename(filename: str) -> str:
    """Очищает имя файла от небезопасных символов и лишних подчёркиваний"""
    import re
    # Заменяем пробелы и скобки на подчёркивание
    safe_name = re.sub(r'[\s()]+', '_', filename)
    # Убираем все остальные небезопасные символы
    safe_name = re.sub(r'[^\w\-_.]', '', safe_name)
    # Убираем повторяющиеся подчёркивания
    safe_name = re.sub(r'_+', '_', safe_name)
    # Убираем подчёркивания в начале и конце
    safe_name = safe_name.strip('_')
    # Ограничиваем длину
    if len(safe_name) > 100:
        name, ext = os.path.splitext(safe_name)
        safe_name = name[:95] + ext
    return safe_name

def create_progress_bar(current: int, total: int, width: int = 20) -> str:
    """Создает текстовый прогресс-бар"""
    if total == 0:
        return "[" + " " * width + "] 0%"
    
    progress = int((current / total) * width)
    bar = "█" * progress + "░" * (width - progress)
    percentage = int((current / total) * 100)
    return f"[{bar}] {percentage}%" 