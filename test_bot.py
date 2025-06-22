#!/usr/bin/env python3
"""
Тестовый скрипт для проверки основных функций TenderBot
"""

import asyncio
import logging
from pathlib import Path

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
        
        return True
    except Exception as e:
        print(f"❌ Ошибка тестирования модуля анализа: {e}")
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
        ("API подключения", test_api_connections),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Ошибка выполнения теста {test_name}: {e}")
            results.append((test_name, False))
    
    # Выводим итоговые результаты
    print("\n" + "=" * 50)
    print("📊 Результаты тестов:")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ ПРОЙДЕН" if result else "❌ ПРОВАЛЕН"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\nИтого: {passed}/{total} тестов пройдено")
    
    if passed == total:
        print("🎉 Все тесты пройдены! Бот готов к работе.")
        return True
    else:
        print("⚠️ Некоторые тесты не пройдены. Проверьте настройки.")
        return False

if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1) 