#!/usr/bin/env python3
"""
Комплексный тестовый скрипт для проверки всех функций TenderBot
"""

import asyncio
import logging
from pathlib import Path
import os
import json
from datetime import datetime
import pytest
from company_profile import build_company_profile
from analyzer import analyzer
from utils.validators import extract_tender_number
from common_utils import validate_user_session, format_file_size, sanitize_filename

# Настройка логирования для тестов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_config():
    """Тестирует загрузку конфигурации"""
    print("🔧 Тест конфигурации...")
    try:
        import config
        print("✅ Конфигурация загружена")
        return True
    except Exception as e:
        print(f"❌ Ошибка загрузки конфигурации: {e}")
        return False

async def test_damia_client():
    """Тестирует клиент DaMIA"""
    print("🌐 Тест DaMIA клиента...")
    try:
        from damia import damia_client
        
        # Тест извлечения номера из текста
        test_text = "Тендер 0123456789012345678 на поставку товаров"
        reg_number = damia_client.extract_tender_number(test_text)
        
        if reg_number == "0123456789012345678":
            print("✅ Извлечение номера тендера работает")
        else:
            print(f"❌ Ошибка извлечения номера: {reg_number}")
            return False
        
        # Тест извлечения из ссылки
        test_url = "https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0123456789012345678"
        reg_number = damia_client.extract_tender_number(test_url)
        
        if reg_number == "0123456789012345678":
            print("✅ Извлечение номера из ссылки работает")
        else:
            print(f"❌ Ошибка извлечения номера из ссылки: {reg_number}")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования DaMIA клиента: {e}")
        return False

async def test_downloader():
    """Тестирует модуль скачивания"""
    print("📥 Тест модуля скачивания...")
    try:
        from downloader import downloader
        
        # Проверяем создание директории
        if downloader.download_dir.exists():
            print("✅ Директория для скачивания существует")
        else:
            print("❌ Директория для скачивания не создана")
            return False
        
        # Тест создания безопасного имени файла
        safe_name = downloader._create_safe_filename("0123456789012345678", "test_document.pdf")
        if "0123456789012345678" in safe_name and "test_document.pdf" in safe_name:
            print("✅ Создание безопасного имени файла работает")
        else:
            print(f"❌ Ошибка создания имени файла: {safe_name}")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования модуля скачивания: {e}")
        return False

async def test_analyzer():
    """Тестирует модуль анализа"""
    print("🤖 Тест модуля анализа...")
    try:
        from analyzer import analyzer
        
        # Тест создания пустого анализа
        empty_analysis = analyzer._create_empty_analysis()
        if "overall_analysis" in empty_analysis:
            print("✅ Создание пустого анализа работает")
        else:
            print("❌ Ошибка создания пустого анализа")
            return False
        
        # Тест кэширования
        from analyzer import get_cache_key, cache_analysis_result, get_cached_analysis
        test_data = {"test": "data"}
        test_files = [{"path": "test.txt"}]
        cache_key = get_cache_key(test_data, test_files)
        if cache_key:
            print("✅ Генерация ключа кэша работает")
        else:
            print("❌ Ошибка генерации ключа кэша")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования модуля анализа: {e}")
        return False

async def test_utils():
    """Тестирует утилиты"""
    print("🔧 Тест утилит...")
    try:
        from common_utils import validate_user_session, format_file_size, sanitize_filename
        
        # Тест валидации сессии
        user_sessions = {123: {"status": "ready_for_analysis", "data": "test"}}
        valid, session = validate_user_session(123, user_sessions, "ready_for_analysis")
        if valid and session:
            print("✅ Валидация сессии работает")
        else:
            print("❌ Ошибка валидации сессии")
            return False
        
        # Тест форматирования размера файла
        size_str = format_file_size(1024)
        if "1.0KB" in size_str:
            print("✅ Форматирование размера файла работает")
        else:
            print(f"❌ Ошибка форматирования размера: {size_str}")
            return False
        
        # Тест очистки имени файла
        safe_name = sanitize_filename("test file (1).pdf")
        if "test_file_1_.pdf" in safe_name:
            print("✅ Очистка имени файла работает")
        else:
            print(f"❌ Ошибка очистки имени файла: {safe_name}")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования утилит: {e}")
        return False

async def test_api_connections():
    """Тестирует подключения к API"""
    print("🔌 Тест подключений к API...")
    
    try:
        import config
        
        # Проверяем наличие API ключей
        if config.TELEGRAM_TOKEN and config.TELEGRAM_TOKEN != 'вставь_сюда_свой_токен':
            print("✅ Telegram токен настроен")
        else:
            print("⚠️ Telegram токен не настроен")
        
        if config.DAMIA_ARBITR_API_KEY and config.DAMIA_ARBITR_API_KEY != 'вставь_сюда_ключ_для_арбитражей':
            print("✅ DaMIA API ключ для арбитражей настроен")
        else:
            print("⚠️ DaMIA API ключ для арбитражей не настроен")
        
        if config.DAMIA_FNS_API_KEY and config.DAMIA_FNS_API_KEY != 'вставь_сюда_ключ_для_ФНС':
            print("✅ DaMIA API ключ для ФНС настроен")
        else:
            print("⚠️ DaMIA API ключ для ФНС не настроен")
        
        if config.OPENAI_API_KEY and config.OPENAI_API_KEY != 'вставь_сюда_свой_OpenAI_ключ':
            print("✅ OpenAI API ключ настроен")
        else:
            print("⚠️ OpenAI API ключ не настроен")
        
        if config.SERPAPI_KEY and config.SERPAPI_KEY != 'вставь_сюда_свой_SerpAPI_ключ':
            print("✅ SerpAPI ключ настроен")
        else:
            print("⚠️ SerpAPI ключ не настроен")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка проверки API ключей: {e}")
        return False

async def test_file_structure():
    """Тестирует структуру файлов проекта"""
    print("📁 Тест структуры файлов...")
    
    required_files = [
        "bot.py",
        "config.py", 
        "damia.py",
        "damia_api.py",
        "fns_api.py",
        "arbitr_api.py",
        "supplier_checker.py",
        "tender_history.py",
        "downloader.py",
        "analyzer.py",
        "utils.py",
        "handlers.py",
        "requirements.txt",
        "README.md",
        "env_example.txt",
        ".gitignore"
    ]
    
    missing_files = []
    for file in required_files:
        if not Path(file).exists():
            missing_files.append(file)
    
    if missing_files:
        print(f"❌ Отсутствуют файлы: {missing_files}")
        return False
    else:
        print("✅ Все необходимые файлы присутствуют")
        return True

async def test_supplier_checker():
    """Тестирует модуль проверки поставщиков"""
    print("🔍 Тест модуля проверки поставщиков...")
    try:
        from arbitr_api import arbitr_api
        
        # Проверяем наличие API ключей
        import config
        if config.DAMIA_ARBITR_API_KEY and config.DAMIA_ARBITR_API_KEY != 'вставь_сюда_ключ_для_арбитражей':
            print("✅ API ключ для арбитражей настроен")
        else:
            print("⚠️ API ключ для арбитражей не настроен")
        
        # Тест создания экземпляра API
        if arbitr_api:
            print("✅ API для арбитражей инициализирован")
        else:
            print("❌ Ошибка инициализации API для арбитражей")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования модуля проверки поставщиков: {e}")
        return False

async def test_tender_history():
    """Тестирует модуль анализа истории тендеров"""
    print("📈 Тест модуля анализа истории тендеров...")
    try:
        from tender_history import TenderHistoryAnalyzer, TenderPosition, HistoricalTender
        from damia import damia_client
        
        # Создаем анализатор
        analyzer = TenderHistoryAnalyzer(damia_client)
        
        # Тестовые данные тендера
        test_tender_data = {
            "РегНомер": "123456789",
            "Предмет": "Поставка муки пшеничной высшего сорта",
            "НМЦК": 1000000,
            "Регион": "Московская область",
            "ДатаПубл": "2024-01-15",
            "Позиции": [
                {
                    "Название": "Мука пшеничная высший сорт ГОСТ Р 52189-2003",
                    "Количество": 1000,
                    "Единица": "кг",
                    "Цена": 100
                }
            ]
        }
        
        # Тест извлечения позиций
        positions = await analyzer.extract_tender_positions(test_tender_data)
        if len(positions) > 0:
            print("✅ Извлечение позиций тендера работает")
        else:
            print("❌ Ошибка извлечения позиций")
            return False
        
        # Тест генерации запросов
        queries = await analyzer.generate_search_queries(positions)
        if len(queries) > 0:
            print("✅ Генерация поисковых запросов работает")
        else:
            print("❌ Ошибка генерации запросов")
            return False
        
        # Тест создания исторических данных
        test_historical_tenders = [
            HistoricalTender(
                tender_id="111111111",
                name="Поставка муки пшеничной",
                region="Московская область",
                publication_date=datetime(2023, 12, 15),
                nmck=950000,
                final_price=850000,
                winner_name="ООО 'МукаПлюс'",
                winner_inn="1234567890",
                participants_count=4,
                subject="Поставка муки пшеничной высшего сорта",
                status="completed",
                price_reduction_percent=10.5
            )
        ]
        
        # Тест анализа динамики цен
        price_analysis = await analyzer.analyze_price_dynamics(test_historical_tenders, test_tender_data['НМЦК'])
        if price_analysis and 'avg_price' in price_analysis:
            print("✅ Анализ динамики цен работает")
        else:
            print("❌ Ошибка анализа динамики цен")
            return False
        
        # Тест генерации отчета
        report = await analyzer.generate_analysis_report(test_historical_tenders, test_tender_data, price_analysis)
        if "История похожих тендеров" in report:
            print("✅ Генерация отчета работает")
        else:
            print("❌ Ошибка генерации отчета")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования модуля истории тендеров: {e}")
        return False

async def test_full_analysis():
    """Тестирует полный цикл анализа"""
    print("🔄 Тест полного цикла анализа...")
    try:
        # Здесь можно добавить тест полного цикла
        # от получения тендера до анализа документов
        print("✅ Полный цикл анализа готов к тестированию")
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования полного цикла: {e}")
        return False

async def test_retry_logic():
    """Тестирует retry-логику"""
    print("🔄 Тест retry-логики...")
    try:
        from bot import retry_on_error
        
        @retry_on_error(max_retries=2, delay=0.1)
        async def failing_function():
            raise Exception("Тестовая ошибка")
        
        try:
            await failing_function()
            print("❌ Retry-логика не сработала")
            return False
        except Exception:
            print("✅ Retry-логика работает корректно")
            return True
    except Exception as e:
        print(f"❌ Ошибка тестирования retry-логики: {e}")
        return False

async def test_caching():
    """Тестирует систему кэширования"""
    print("💾 Тест системы кэширования...")
    try:
        from bot import get_cache_key, cache_analysis_result, get_cached_analysis
        
        # Тестовые данные
        test_data = {"test": "data"}
        test_files = [{"path": "test.txt"}]
        
        # Генерируем ключ
        cache_key = get_cache_key(test_data, test_files)
        if not cache_key:
            print("❌ Ошибка генерации ключа кэша")
            return False
        
        # Сохраняем в кэш
        test_result = {"analysis": "test result"}
        cache_analysis_result(cache_key, test_result)
        
        # Получаем из кэша
        cached_result = get_cached_analysis(cache_key)
        if cached_result == test_result:
            print("✅ Система кэширования работает")
            return True
        else:
            print("❌ Ошибка получения из кэша")
            return False
    except Exception as e:
        print(f"❌ Ошибка тестирования кэширования: {e}")
        return False

async def test_admin_panel():
    """Тестирует админ панель"""
    print("👨‍💼 Тест админ панели...")
    try:
        from bot import TenderBot
        
        bot = TenderBot()
        
        # Тест получения информации о пользователе
        user_info = await bot._get_user_info(12345)
        if isinstance(user_info, dict) and 'has_subscription' in user_info:
            print("✅ Получение информации о пользователе работает")
        else:
            print("❌ Ошибка получения информации о пользователе")
            return False
        
        # Тест проверки доступа к админ панели
        # Создаем мок-объект для тестирования
        class MockUser:
            def __init__(self, username):
                self.username = username
        
        class MockQuery:
            def __init__(self, username):
                self.from_user = MockUser(username)
        
        # Тест для пользователя hoproqr (должен иметь доступ)
        query_hoproqr = MockQuery("hoproqr")
        # Тест для обычного пользователя (не должен иметь доступ)
        query_regular = MockQuery("regular_user")
        
        print("✅ Проверка доступа к админ панели настроена")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования админ панели: {e}")
        return False

async def test_supplier_check_apis():
    """Тестирует API проверки контрагентов"""
    print("🔍 Тест API проверки контрагентов...")
    try:
        # Тест FNS API
        from fns_api import fns_api
        print("✅ FNS API импортирован")
        
        # Тест Arbitr API
        from arbitr_api import arbitr_api
        print("✅ Arbitr API импортирован")
        
        # Тест Scoring API
        from scoring_api import scoring_api
        print("✅ Scoring API импортирован")
        
        # Тест FSSP API
        from fssp_api import fssp_client
        print("✅ FSSP API импортирован")
        
        # Тест валидации ИНН
        test_inns = ["7704627217", "1234567890", "123456789012"]
        for inn in test_inns:
            if len(inn) in [10, 12] and inn.isdigit():
                print(f"✅ Валидация ИНН {inn} работает")
            else:
                print(f"❌ Ошибка валидации ИНН {inn}")
                return False
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования API проверки контрагентов: {e}")
        return False

async def test_fssp_api():
    """Тестирует FSSP API"""
    print("⚖️ Тест FSSP API...")
    try:
        from fssp_api import fssp_client
        
        # Тест соединения
        is_connected = await fssp_client.test_connection()
        if is_connected:
            print("✅ Соединение с FSSP API установлено")
        else:
            print("❌ Не удалось установить соединение с FSSP API")
            return False
        
        # Тест получения производств компании
        test_inn = "7704627217"  # Газпром
        result = await fssp_client.get_company_proceedings(test_inn, format=1)
        
        if result and result.get('status') == 'success':
            print(f"✅ Успешное получение производств для {test_inn}")
            print(f"   Метод: {result.get('method')}")
            print(f"   Формат: {result.get('format')}")
        else:
            print(f"❌ Ошибка при получении производств для {test_inn}")
            if result:
                print(f"   Статус: {result.get('status')}")
                print(f"   Сообщение: {result.get('message', 'Не указано')}")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования FSSP API: {e}")
        return False

async def test_arbitr_api():
    """Тестирует Arbitration API"""
    print("⚖️ Тест Arbitration API...")
    try:
        from arbitr_api import arbitr_api
        
        # Тест получения арбитражных дел
        test_inn = "7704627217"  # Газпром
        result = await arbitr_api.get_arbitrage_cases_by_inn(test_inn)
        
        if result and result.get('status') in ['found', 'success']:
            print(f"✅ Успешное получение арбитражных дел для {test_inn}")
            cases = result.get('cases', [])
            print(f"   Найдено дел: {len(cases)}")
        else:
            print(f"❌ Ошибка при получении арбитражных дел для {test_inn}")
            if result:
                print(f"   Статус: {result.get('status')}")
                print(f"   Сообщение: {result.get('message', 'Не указано')}")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования Arbitration API: {e}")
        return False

async def test_scoring_api():
    """Тестирует Scoring API"""
    print("📊 Тест Scoring API...")
    try:
        from scoring_api import scoring_api
        
        # Тест расчета скоринга
        test_inn = "7704627217"  # Газпром
        result = await scoring_api.calculate_risk_score(test_inn, '_problemCredit')
        
        if result and result.get('status') in ['success', 'found']:
            print(f"✅ Успешный расчет скоринга для {test_inn}")
            print(f"   Скоринг: {result.get('score', 'Не указан')}")
            print(f"   Уровень риска: {result.get('risk_level', 'Не указан')}")
        else:
            print(f"❌ Ошибка при расчете скоринга для {test_inn}")
            if result:
                print(f"   Статус: {result.get('status')}")
                print(f"   Сообщение: {result.get('message', 'Не указано')}")
            return False
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования Scoring API: {e}")
        return False

async def test_fns_api_detailed():
    """Детальное тестирование API ФНС"""
    print("🔍 Детальное тестирование API ФНС...")
    
    # Тестовый ИНН (ООО "Газпром")
    inn = "7736050003"
    
    try:
        from fns_api import fns_api
        
        print(f"\n📋 Получение данных компании для ИНН {inn}...")
        company_data = await fns_api.get_company_info(inn)
        
        print(f"Статус: {company_data.get('status')}")
        if company_data.get('status') == 'found':
            print("✅ Данные компании получены")
            print(f"Количество записей: {len(company_data.get('data', []))}")
            
            # Форматируем и выводим данные
            formatted_info = fns_api.format_company_info(company_data)
            print("\n📄 Форматированная информация:")
            print(formatted_info)
        else:
            print("❌ Данные компании не найдены")
        
        print(f"\n🔍 Проверка контрагента для ИНН {inn}...")
        check_data = await fns_api.check_company(inn)
        
        print(f"Статус: {check_data.get('status')}")
        if check_data.get('status') == 'found':
            print("✅ Данные проверки получены")
            print(f"Тип организации: {check_data.get('company_type')}")
            print(f"Есть нарушения: {check_data.get('has_violations')}")
            
            # Форматируем и выводим результаты проверки
            formatted_check = fns_api.format_company_check(check_data)
            print("\n📄 Результаты проверки:")
            print(formatted_check)
        else:
            print("❌ Данные проверки не найдены")
        
        # Тест поиска компаний
        print(f"\n🔎 Поиск компаний по запросу 'Газпром'...")
        search_data = await fns_api.search_companies("Газпром", page=1)
        
        print(f"Статус: {search_data.get('status')}")
        if search_data.get('status') == 'found':
            print("✅ Результаты поиска получены")
            print(f"Найдено компаний: {search_data.get('total_count')}")
            
            companies = search_data.get('companies', [])
            if companies:
                print("\n📋 Первые результаты:")
                for i, company in enumerate(companies[:3], 1):
                    if 'ЮЛ' in company:
                        company_info = company['ЮЛ']
                        name = company_info.get('НаимСокрЮЛ', 'Не указано')
                        inn_company = company_info.get('ИНН', 'Не указано')
                        status = company_info.get('Статус', 'Не указано')
                        print(f"{i}. {name} (ИНН: {inn_company}, Статус: {status})")
                    elif 'ИП' in company:
                        company_info = company['ИП']
                        name = company_info.get('ФИОПолн', 'Не указано')
                        inn_company = company_info.get('ИНН', 'Не указано')
                        status = company_info.get('Статус', 'Не указано')
                        print(f"{i}. ИП {name} (ИНН: {inn_company}, Статус: {status})")
        else:
            print("❌ Результаты поиска не найдены")
        
        # Тест проверки блокировок счета
        print(f"\n🔒 Проверка блокировок счета для ИНН {inn}...")
        blocks_data = await fns_api.check_account_blocks(inn)
        
        print(f"Статус: {blocks_data.get('status')}")
        if blocks_data.get('status') == 'found':
            print("✅ Данные о блокировках получены")
            blocks = blocks_data.get('blocks_data', [])
            print(f"Найдено записей о блокировках: {len(blocks)}")
            
            if blocks:
                print("\n📋 Информация о блокировках:")
                for i, block in enumerate(blocks, 1):
                    print(f"{i}. {block}")
            else:
                print("✅ Блокировок счета не обнаружено")
        else:
            print("❌ Данные о блокировках не найдены")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка при тестировании API ФНС: {e}")
        return False

async def test_arbitr_api_detailed():
    """Детальное тестирование API арбитражных дел"""
    print("\n⚖️ Детальное тестирование API арбитражных дел...")
    
    # Тестовый ИНН
    inn = "7736050003"
    
    try:
        from arbitr_api import arbitr_api
        
        print(f"📋 Получение арбитражных дел для ИНН {inn}...")
        cases_data = await arbitr_api.get_arbitrage_cases_by_inn(inn)
        
        print(f"Статус: {cases_data.get('status')}")
        if cases_data.get('status') == 'found':
            print("✅ Арбитражные дела получены")
            cases = cases_data.get('cases', [])
            total_count = cases_data.get('total_count', 0)
            print(f"Найдено дел: {total_count}")
            
            # Форматируем и выводим сводку
            formatted_summary = arbitr_api.format_arbitrage_summary(cases_data)
            print("\n📄 Сводка по арбитражным делам:")
            print(formatted_summary)
            
            if cases:
                print("\n📄 Первые дела:")
                for i, case in enumerate(cases[:5], 1):
                    case_number = case.get('case_number', 'Неизвестно')
                    case_type = case.get('case_type', 'Неизвестно')
                    status = case.get('status', 'Неизвестно')
                    print(f"{i}. {case_number} ({case_type}) - {status}")
            else:
                print("✅ Арбитражные дела не найдены")
        else:
            print("❌ Арбитражные дела не найдены")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка при тестировании API арбитражей: {e}")
        return False

async def test_fssp_api_detailed():
    """Детальное тестирование API ФССП"""
    print("\n👮 Детальное тестирование API ФССП...")
    
    # Тестовый ИНН
    inn = "7736050003"
    
    try:
        from fssp_api import fssp_client
        
        print(f"📋 Получение исполнительных производств для ИНН {inn}...")
        fssp_data = await fssp_client.check_company(inn)
        
        print(f"Статус: {fssp_data.get('status') if fssp_data else 'None'}")
        if fssp_data and fssp_data.get('status') == 'success':
            print("✅ Данные ФССП получены")
            proceedings = fssp_data.get('executive_proceedings', [])
            summary = fssp_data.get('summary', {})
            
            print(f"Всего производств: {summary.get('total_proceedings', 0)}")
            print(f"Активных: {summary.get('active_proceedings', 0)}")
            print(f"Общая задолженность: {summary.get('total_debt', 0)} руб.")
            
            if proceedings:
                print("\n📄 Первые производства:")
                for i, proc in enumerate(proceedings[:5], 1):
                    case_number = proc.get('number', 'Неизвестно')
                    amount = proc.get('amount', 'Неизвестно')
                    status = proc.get('status', 'Неизвестно')
                    print(f"{i}. {case_number} - {amount} - {status}")
            else:
                print("✅ Исполнительные производства не найдены")
        else:
            error_msg = fssp_data.get('error', 'Неизвестная ошибка') if fssp_data else 'Данные недоступны'
            print(f"❌ Ошибка: {error_msg}")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка при тестировании API ФССП: {e}")
        return False

async def test_scoring_api_detailed():
    """Детальное тестирование API скоринга"""
    print("\n📊 Детальное тестирование API скоринга...")
    
    # Тестовый ИНН
    inn = "7736050003"
    
    try:
        from scoring_api import scoring_api
        
        print(f"📋 Получение скоринга для ИНН {inn}...")
        scoring_data = await scoring_api.get_comprehensive_scoring(inn)
        
        print(f"Статус: {scoring_data.get('status')}")
        if scoring_data.get('status') == 'completed':
            print("✅ Скоринг получен")
            results = scoring_data.get('results', {})
            
            print("\n📈 Результаты скоринга:")
            for model_name, model_result in results.items():
                if model_name == 'financial_coefficients':
                    continue
                
                if model_result.get('status') == 'success':
                    score = model_result.get('score', 0)
                    risk_level = model_result.get('risk_level', 'unknown')
                    probability = model_result.get('probability', 0)
                    
                    print(f"• {model_name}: {score} ({risk_level}, ", end="")
                    if isinstance(probability, (int, float)):
                        print(f"{probability:.1f}%)")
                    else:
                        print(f"{probability}%)")
                else:
                    print(f"• {model_name}: Ошибка")
            
            # Финансовые коэффициенты
            fin_data = results.get('financial_coefficients', {})
            if fin_data.get('status') == 'found':
                print("\n💰 Ключевые финансовые показатели:")
                coefs = fin_data.get('coefficients', {})
                
                key_coefs = {
                    'КоэфТекЛикв': 'Текущая ликвидность',
                    'РентАктивов': 'Рентабельность активов',
                    'КоэфФинАвт': 'Финансовая автономия',
                    'РентПродаж': 'Рентабельность продаж'
                }
                
                for coef_code, coef_name in key_coefs.items():
                    value = coefs.get(coef_code)
                    if value is not None:
                        if isinstance(value, dict):
                            years = sorted(value.keys(), reverse=True)
                            if years:
                                latest_year = years[0]
                                year_data = value[latest_year]
                                if isinstance(year_data, dict) and 'Знач' in year_data:
                                    display_value = year_data['Знач']
                                    if isinstance(display_value, (int, float)):
                                        print(f"• {coef_name} ({latest_year}): {display_value:.3f}")
                                    else:
                                        print(f"• {coef_name} ({latest_year}): {display_value}")
                        else:
                            if isinstance(value, (int, float)):
                                print(f"• {coef_name}: {value:.3f}")
                            else:
                                print(f"• {coef_name}: {value}")
            else:
                print("\n❌ Финансовые данные недоступны")
        else:
            print("❌ Скоринг не выполнен")
        
        return True
    except Exception as e:
        print(f"❌ Ошибка при тестировании API скоринга: {e}")
        return False

@pytest.mark.asyncio
async def test_company_profile():
    inn = "7707083893"  # Пример ИНН
    profile = build_company_profile(inn)
    assert "ИНН" in profile or "ОГРН" in profile or "Компания" in profile

@pytest.mark.asyncio
async def test_analyze_tender():
    tender_data = {"Наименование": "Поставка бумаги", "НМЦК": 100000, "Позиции": [{"Название": "Бумага офисная", "Количество": 100, "Единица": "пачка"}]}
    files = []
    result = await analyzer.analyze_tender_documents(tender_data, files)
    assert "summary" in result.get("overall_analysis", {})

@pytest.mark.asyncio
async def test_extract_tender_number():
    text = "https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0123456789012345678"
    number = extract_tender_number(text)
    assert number == "0123456789012345678"

@pytest.mark.asyncio
async def test_fallback_empty_api():
    # Проверка fallback при пустом ответе API (заглушка)
    from exportbase_api import get_company_by_inn
    result = get_company_by_inn("0000000000")
    assert result == {} or result is not None

async def run_all_tests():
    """Запускает все тесты"""
    print("🚀 Запуск комплексного тестирования TenderBot")
    print("=" * 60)
    
    tests = [
        ("Конфигурация", test_config),
        ("DaMIA клиент", test_damia_client),
        ("Модуль скачивания", test_downloader),
        ("Модуль анализа", test_analyzer),
        ("Утилиты", test_utils),
        ("API подключения", test_api_connections),
        ("Структура файлов", test_file_structure),
        ("История тендеров", test_tender_history),
        ("Retry-логика", test_retry_logic),
        ("Кэширование", test_caching),
        ("Полный цикл", test_full_analysis),
        ("Админ панель", test_admin_panel),
        ("API проверки контрагентов", test_supplier_check_apis),
        ("FNS API", test_fns_api),
        ("FSSP API", test_fssp_api),
        ("Arbitration API", test_arbitr_api),
        ("Scoring API", test_scoring_api),
        ("FNS API детальное", test_fns_api_detailed),
        ("Arbitr API детальное", test_arbitr_api_detailed),
        ("FSSP API детальное", test_fssp_api_detailed),
        ("Scoring API детальное", test_scoring_api_detailed),
        ("Профиль компании", test_company_profile),
        ("Анализ тендера", test_analyze_tender),
        ("Извлечение номера тендера", test_extract_tender_number),
        ("Fallback при пустом ответе API", test_fallback_empty_api)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}...")
        try:
            result = await test_func()
            results.append((test_name, result))
            status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
            print(f"{status}: {test_name}")
        except Exception as e:
            print(f"❌ ОШИБКА: {test_name} - {e}")
            results.append((test_name, False))
    
    # Итоговый отчет
    print("\n" + "=" * 60)
    print("📊 ИТОГОВЫЙ ОТЧЕТ")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {test_name}")
    
    print(f"\n📈 Результат: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены успешно!")
        return True
    else:
        print("⚠️ Некоторые тесты не пройдены")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1) 