#!/usr/bin/env python3
"""
Тестовый скрипт для проверки исправлений API
"""

import asyncio
import logging
from config import FNS_API_KEY
from fns_api import fns_api
from arbitr_api import arbitr_api
from fssp_api import fssp_client
from scoring_api import scoring_api

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

async def test_fns_api():
    """Тестирование API ФНС"""
    print("🔍 Тестирование API ФНС...")
    
    # Тестовый ИНН (ООО "Газпром")
    inn = "7736050003"
    
    try:
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
        
    except Exception as e:
        print(f"❌ Ошибка при тестировании API ФНС: {e}")
        logger.error(f"Ошибка при тестировании API ФНС: {e}")

async def test_arbitr_api():
    """Тестирование API арбитражных дел"""
    print("\n⚖️ Тестирование API арбитражных дел...")
    
    # Тестовый ИНН
    inn = "7736050003"
    
    try:
        print(f"📋 Получение арбитражных дел для ИНН {inn}...")
        cases_data = await arbitr_api.get_arbitrage_cases_by_inn(inn)
        
        print(f"Статус: {cases_data.get('status')}")
        if cases_data.get('status') == 'found':
            print("✅ Арбитражные дела получены")
            cases = cases_data.get('cases', [])
            total_count = cases_data.get('total_count', 0)
            print(f"Найдено дел: {total_count}")
            
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
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании API арбитражей: {e}")
        logger.error(f"Ошибка при тестировании API арбитражей: {e}")

async def test_fssp_api():
    """Тестирование API ФССП"""
    print("\n👮 Тестирование API ФССП...")
    
    # Тестовый ИНН
    inn = "7736050003"
    
    try:
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
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании API ФССП: {e}")
        logger.error(f"Ошибка при тестировании API ФССП: {e}")

async def test_scoring_api():
    """Тестирование API скоринга"""
    print("\n📊 Тестирование API скоринга...")
    
    # Тестовый ИНН
    inn = "7736050003"
    
    try:
        print(f"📋 Получение скоринга для ИНН {inn}...")
        scoring_data = await scoring_api.get_comprehensive_scoring(inn)
        
        print(f"Статус: {scoring_data.get('status')}")
        if scoring_data.get('status') == 'completed':
            print("✅ Скоринг получен")
            results = scoring_data.get('results', {})
            
            print("\n📈 Результаты скоринга:")
            for model_name, model_result in results.items():
                if model_result.get('status') == 'success':
                    score = model_result.get('score', 0)
                    risk_level = model_result.get('risk_level', 'unknown')
                    probability = model_result.get('probability', 0)
                    print(f"• {model_name}: {score} ({risk_level}, {probability:.1f}%)")
                else:
                    print(f"• {model_name}: Ошибка")
        else:
            print("❌ Скоринг не получен")
            
    except Exception as e:
        print(f"❌ Ошибка при тестировании API скоринга: {e}")
        logger.error(f"Ошибка при тестировании API скоринга: {e}")

async def main():
    """Основная функция тестирования"""
    print("🚀 Запуск тестирования API...")
    print(f"🔑 API ключ ФНС: {'Установлен' if FNS_API_KEY and FNS_API_KEY != 'вставь_сюда_ключ_для_ФНС' else 'НЕ УСТАНОВЛЕН'}")
    
    # Тестируем все API
    await test_fns_api()
    await test_arbitr_api()
    await test_fssp_api()
    await test_scoring_api()
    
    print("\n✅ Тестирование завершено!")

if __name__ == "__main__":
    asyncio.run(main()) 