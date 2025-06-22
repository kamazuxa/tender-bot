import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Telegram Bot Token
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'вставь_сюда_свой_токен')

# DaMIA API
DAMIA_API_KEY = os.getenv('DAMIA_API_KEY', 'вставь_сюда_свой_API_ключ')

# OpenAI API
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'вставь_сюда_свой_OpenAI_ключ')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

# Настройки приложения
DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
SUPPORTED_EXTENSIONS = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.jpeg', '.jpg', '.png', '.zip', '.rar']

# Настройки логирования
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = 'tender_bot.log'

# Настройки VPN (для OpenAI запросов)
USE_VPN_FOR_OPENAI = os.getenv('USE_VPN_FOR_OPENAI', 'true').lower() == 'true'
VPN_INTERFACE = os.getenv('VPN_INTERFACE', 'wg0')

# Настройки подписки (для будущего развития)
TRIAL_DAYS = 7
SUBSCRIPTION_PRICE = 999  # рублей в месяц 