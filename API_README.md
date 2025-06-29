# 📋 API Сервисы DaMIA в TenderBot

TenderBot использует несколько API сервисов от DaMIA для комплексной проверки поставщиков и анализа тендеров.

## 🔧 Настройка API ключей

В файле `config.py` настройте следующие переменные:

```python
# Основной API для закупок
DAMIA_API_KEY = 'ваш_ключ_для_закупок'

# API для проверки поставщиков (ФНС)
DAMIA_SUPPLIER_API_KEY = 'ваш_ключ_для_проверки_поставщиков'
DAMIA_SUPPLIER_BASE_URL = 'https://api-fns.ru/api'

# API для ФНС (ЕГРЮЛ/ЕГРИП)
DAMIA_FNS_API_KEY = 'ваш_ключ_для_ФНС'
DAMIA_FNS_BASE_URL = 'https://api-fns.ru/api'

# API для арбитражных дел
DAMIA_ARBITR_API_KEY = 'ваш_ключ_для_арбитражей'
DAMIA_ARBITR_BASE_URL = 'https://api.damia.ru/arb'
```

## 📊 Доступные API сервисы

### 1. API-Закупки (`damia.py`)
- **Назначение**: Получение данных о тендерах и закупках
- **Методы**: 
  - `get_zakupka()` - информация о закупке
  - `get_contract()` - информация о контракте
  - `zsearch()` - поиск тендеров

### 2. API-ФНС (`fns_api.py`)
- **Назначение**: Проверка компаний через ЕГРЮЛ/ЕГРИП
- **Методы**:
  - `search_companies()` - поиск компаний
  - `get_company_info()` - данные компании
  - `check_company()` - проверка контрагента
  - `get_company_changes()` - отслеживание изменений
  - `get_inn_by_passport()` - ИНН по паспорту
  - `check_passport_validity()` - проверка паспорта

### 3. API-Арбитражи (`arbitr_api.py`)
- **Назначение**: Проверка арбитражных дел
- **Методы**:
  - `get_arbitrage_case()` - информация о деле
  - `get_arbitrage_cases_by_inn()` - дела по ИНН
  - `track_arbitrage_case()` - отслеживание дел
  - `get_tracked_cases()` - список отслеживаемых

### 4. API-Проверка поставщиков (`damia_api.py`)
- **Назначение**: Дополнительные проверки поставщиков
- **Методы**:
  - `get_fns()` - проверка ФНС
  - `get_fssp()` - проверка ФССП
  - `get_scoring()` - финансовый скоринг

## 🔍 Использование в коде

### Проверка поставщика
```python
from supplier_checker import check_supplier

# Комплексная проверка поставщика
result = await check_supplier("1234567890")
print(result['risk'])  # Уровень риска
```

### Поиск компаний
```python
from fns_api import fns_api

# Поиск компаний
companies = await fns_api.search_companies("ООО Рога и Копыта")
```

### Проверка арбитражных дел
```python
from arbitr_api import arbitr_api

# Арбитражные дела компании
cases = await arbitr_api.get_arbitrage_cases_by_inn("1234567890")
```

## ⚠️ Важные замечания

1. **Разные ключи**: Каждый API сервис требует отдельный ключ
2. **Лимиты**: У каждого API есть свои лимиты запросов
3. **Кэширование**: Результаты кэшируются для экономии ресурсов
4. **Retry-логика**: Автоматические повторные попытки при ошибках

## 🚀 Получение API ключей

1. **API-Закупки**: https://damia.ru
2. **API-ФНС**: https://api-fns.ru
3. **API-Арбитражи**: https://damia.ru/arb
4. **API-Проверка поставщиков**: https://damia.ru/supplier

## 📝 Примеры запросов

### Проверка контрагента
```python
from fns_api import fns_api

# Полная проверка компании
company_info = await fns_api.get_company_info("1234567890")
check_result = await fns_api.check_company("1234567890")

print(f"Компания: {company_info['data']['name']}")
print(f"Нарушения: {check_result['violations_count']}")
```

### Анализ арбитражных дел
```python
from arbitr_api import arbitr_api

# Получение арбитражных дел
cases = await arbitr_api.get_arbitrage_cases_by_inn("1234567890")

# Форматирование результата
summary = arbitr_api.format_arbitrage_summary(cases)
print(summary)
``` 