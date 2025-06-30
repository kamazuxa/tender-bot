import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Telegram Bot Token
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', 'вставь_сюда_свой_токен')

# DaMIA API
DAMIA_API_KEY = os.getenv('DAMIA_API_KEY', 'вставь_сюда_свой_API_ключ')
DAMIA_BASE_URL = os.getenv('DAMIA_BASE_URL', 'https://api.damia.ru')

# DaMIA API для проверки поставщиков
DAMIA_SUPPLIER_API_KEY = os.getenv('DAMIA_SUPPLIER_API_KEY', 'вставь_сюда_ключ_для_проверки_поставщиков')
DAMIA_SUPPLIER_BASE_URL = os.getenv('DAMIA_SUPPLIER_BASE_URL', 'https://api.damia.ru/supplier')

# DaMIA API для ФНС (ЕГРЮЛ/ЕГРИП)
DAMIA_FNS_API_KEY = os.getenv('DAMIA_FNS_API_KEY', 'вставь_сюда_ключ_для_ФНС')
DAMIA_FNS_BASE_URL = os.getenv('DAMIA_FNS_BASE_URL', 'https://api-fns.ru/api')

# DaMIA API для арбитражных дел
DAMIA_ARBITR_API_KEY = os.getenv('DAMIA_ARBITR_API_KEY', 'вставь_сюда_ключ_для_арбитражей')
DAMIA_ARBITR_BASE_URL = os.getenv('DAMIA_ARBITR_BASE_URL', 'https://api.damia.ru/arb')

# DaMIA API для скоринга
DAMIA_SCORING_API_KEY = os.getenv('DAMIA_SCORING_API_KEY', 'вставь_сюда_ключ_для_скоринга')
DAMIA_SCORING_BASE_URL = os.getenv('DAMIA_SCORING_BASE_URL', 'https://damia.ru/api-scoring')

# FSSP API для проверки исполнительных производств
FSSP_API_KEY = os.getenv('FSSP_API_KEY', 'вставь_сюда_ключ_для_ФССП')
# Примечание: FSSP API интегрирован через платформу DaMIA
# Используйте тот же ключ, что и для других DaMIA сервисов
FSSP_BASE_URL = os.getenv('FSSP_BASE_URL', 'https://api.fssp.ru')

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

# TenderGuru API
TENDERGURU_API_CODE = os.getenv('TENDERGURU_API_CODE', 'вставь_сюда_свой_TenderGuru_API_ключ') 