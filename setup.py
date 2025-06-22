#!/usr/bin/env python3
"""
Скрипт установки и настройки TenderBot
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def print_banner():
    """Выводит баннер установки"""
    print("""
🤖 TenderBot - Установка и настройка
=====================================

Telegram-бот для анализа тендеров в госзакупках
    """)

def check_python_version():
    """Проверяет версию Python"""
    if sys.version_info < (3, 8):
        print("❌ Требуется Python 3.8 или выше")
        sys.exit(1)
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} - OK")

def install_dependencies():
    """Устанавливает зависимости"""
    print("\n📦 Установка зависимостей...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Зависимости установлены")
    except subprocess.CalledProcessError:
        print("❌ Ошибка установки зависимостей")
        sys.exit(1)

def create_env_file():
    """Создает файл .env из примера"""
    env_example = Path("env_example.txt")
    env_file = Path(".env")
    
    if env_file.exists():
        print("⚠️ Файл .env уже существует")
        return
    
    if not env_example.exists():
        print("❌ Файл env_example.txt не найден")
        return
    
    shutil.copy(env_example, env_file)
    print("✅ Файл .env создан из примера")
    print("📝 Не забудьте заполнить API ключи в файле .env")

def create_directories():
    """Создает необходимые директории"""
    directories = ["downloads", "logs"]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Создана директория: {directory}")

def check_vpn_setup():
    """Проверяет настройку VPN"""
    print("\n🔒 Проверка VPN настройки...")
    
    try:
        result = subprocess.run(["wg", "show"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ WireGuard VPN настроен")
        else:
            print("⚠️ WireGuard VPN не настроен")
            print("   Для работы с OpenAI API рекомендуется настроить VPN")
    except FileNotFoundError:
        print("⚠️ WireGuard не установлен")
        print("   Для работы с OpenAI API рекомендуется установить WireGuard")

def validate_config():
    """Проверяет конфигурацию"""
    print("\n🔧 Проверка конфигурации...")
    
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ Файл .env не найден")
        return False
    
    # Проверяем наличие обязательных переменных
    required_vars = ["TELEGRAM_TOKEN", "DAMIA_API_KEY", "OPENAI_API_KEY"]
    missing_vars = []
    
    with open(env_file, 'r') as f:
        content = f.read()
        for var in required_vars:
            if f"{var}=" not in content or f"{var}=your_" in content:
                missing_vars.append(var)
    
    if missing_vars:
        print(f"⚠️ Не заполнены переменные: {', '.join(missing_vars)}")
        print("   Заполните их в файле .env перед запуском бота")
        return False
    
    print("✅ Конфигурация проверена")
    return True

def run_tests():
    """Запускает базовые тесты"""
    print("\n🧪 Запуск базовых тестов...")
    
    try:
        # Тест импорта модулей
        import config
        import damia
        import downloader
        import analyzer
        print("✅ Все модули импортируются корректно")
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False
    
    return True

def main():
    """Основная функция установки"""
    print_banner()
    
    # Проверяем версию Python
    check_python_version()
    
    # Устанавливаем зависимости
    install_dependencies()
    
    # Создаем директории
    create_directories()
    
    # Создаем файл .env
    create_env_file()
    
    # Проверяем VPN
    check_vpn_setup()
    
    # Проверяем конфигурацию
    config_ok = validate_config()
    
    # Запускаем тесты
    tests_ok = run_tests()
    
    print("\n" + "="*50)
    print("🎉 Установка завершена!")
    
    if config_ok and tests_ok:
        print("\n✅ Бот готов к запуску!")
        print("🚀 Запустите бота командой: python bot.py")
    else:
        print("\n⚠️ Требуется дополнительная настройка:")
        if not config_ok:
            print("   - Заполните API ключи в файле .env")
        if not tests_ok:
            print("   - Исправьте ошибки в коде")
    
    print("\n📖 Подробная документация: README.md")
    print("🔧 Настройка: env_example.txt")

if __name__ == "__main__":
    main() 