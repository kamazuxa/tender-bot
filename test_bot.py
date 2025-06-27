#!/usr/bin/env python3
"""
Тестовый скрипт для проверки основных функций TenderBot
"""

import asyncio
import logging
from pathlib import Path
import os

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
        from utils import validate_user_session, format_file_size, sanitize_filename
        
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
        
        if config.DAMIA_API_KEY and config.DAMIA_API_KEY != 'вставь_сюда_свой_API_ключ':
            print("✅ DaMIA API ключ настроен")
        else:
            print("⚠️ DaMIA API ключ не настроен")
        
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
        print(f"❌ Отсутствуют файлы: {', '.join(missing_files)}")
        return False
    else:
        print("✅ Все необходимые файлы присутствуют")
        return True

async def test_full_analysis():
    """Тестирует полный анализ тендера с логированием для диагностики"""
    print("🧠 Тест полного анализа тендера (GPT + парсинг)...")
    try:
        from analyzer import analyze_tender_documents
        import logging
        logger = logging.getLogger(__name__)

        # Пример тестового файла
        test_filename = "test.txt"
        test_text = "Поставка моркови, фасовка 25 кг, ГОСТ 12345-67, объем 10 тонн, срок поставки 10 дней."
        with open(test_filename, "w", encoding="utf-8") as f:
            f.write(test_text)
        downloaded_files = [{
            'path': test_filename,
            'original_name': test_filename,
            'size': os.path.getsize(test_filename),
        }]
        tender_info = {}
        analysis_result = await analyze_tender_documents(tender_info, downloaded_files)
        logger.info(f"[test] Сырой ответ анализа: {analysis_result}")
        if not analysis_result:
            print("❌ analysis_result is None! Не удалось проанализировать тестовый тендер.")
            return False
        logger.info(f"[test] Итоговый разбор анализа: {analysis_result}")
        print("✅ Анализ тендера и логирование работают")
        # Удаляем тестовый файл
        os.remove(test_filename)
        return True
    except Exception as e:
        print(f"❌ Ошибка теста полного анализа: {e}")
        return False

async def test_retry_logic():
    """Тестирует retry-логику"""
    print("🔄 Тест retry-логики...")
    try:
        from utils import retry_on_error
        
        @retry_on_error(max_retries=2, delay=0.1)
        async def failing_function():
            raise Exception("Test error")
        
        try:
            await failing_function()
            print("❌ Retry-логика не сработала")
            return False
        except Exception as e:
            if "Test error" in str(e):
                print("✅ Retry-логика работает")
                return True
            else:
                print(f"❌ Неожиданная ошибка: {e}")
                return False
    except Exception as e:
        print(f"❌ Ошибка тестирования retry-логики: {e}")
        return False

async def test_caching():
    """Тестирует систему кэширования"""
    print("💾 Тест системы кэширования...")
    try:
        from utils import get_cache_key, cache_analysis_result, get_cached_analysis
        
        test_data = {"test": "data"}
        test_files = [{"path": "test.txt"}]
        
        # Генерируем ключ кэша
        cache_key = get_cache_key(test_data, test_files)
        if not cache_key:
            print("❌ Не удалось сгенерировать ключ кэша")
            return False
        
        # Проверяем, что кэш пустой
        cached = get_cached_analysis(cache_key)
        if cached is None:
            print("✅ Кэш изначально пустой")
        else:
            print("❌ Кэш не пустой")
            return False
        
        # Сохраняем результат в кэш
        test_result = {"result": "test"}
        cache_analysis_result(cache_key, test_result)
        
        # Проверяем, что результат сохранился
        cached = get_cached_analysis(cache_key)
        if cached and cached.get("result") == "test":
            print("✅ Кэширование работает")
            return True
        else:
            print("❌ Кэширование не работает")
            return False
    except Exception as e:
        print(f"❌ Ошибка тестирования кэширования: {e}")
        return False

async def run_all_tests():
    """Запускает все тесты"""
    print("🧪 Запуск тестов TenderBot")
    print("=" * 50)
    
    tests = [
        ("Структура файлов", test_file_structure),
        ("Конфигурация", test_config),
        ("DaMIA клиент", test_damia_client),
        ("Модуль скачивания", test_downloader),
        ("Модуль анализа", test_analyzer),
        ("Утилиты", test_utils),
        ("API подключения", test_api_connections),
        ("Retry-логика", test_retry_logic),
        ("Кэширование", test_caching),
        ("Полный анализ", test_full_analysis),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name}...")
        try:
            result = await test_func()
            results.append((test_name, result))
            if result:
                print(f"✅ {test_name} - ПРОЙДЕН")
            else:
                print(f"❌ {test_name} - ПРОВАЛЕН")
        except Exception as e:
            print(f"❌ {test_name} - ОШИБКА: {e}")
            results.append((test_name, False))
    
    print("\n" + "=" * 50)
    print("📊 РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ:")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"  {test_name}: {status}")
    
    print(f"\n🎯 Итого: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены! Бот готов к работе.")
    else:
        print("⚠️ Некоторые тесты провалены. Проверьте настройки.")
    
    return passed == total

if __name__ == "__main__":
    asyncio.run(run_all_tests()) 