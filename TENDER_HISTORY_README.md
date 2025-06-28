# 📈 Модуль анализа истории похожих тендеров

## 🎯 Описание

Модуль `tender_history.py` предоставляет функциональность для анализа истории похожих тендеров, что позволяет:

- 🔍 Находить похожие тендеры за последние 12 месяцев
- 📊 Анализировать динамику цен
- 🏆 Изучать победителей и условия
- 📈 Сравнивать текущий тендер с историческими данными
- 📋 Генерировать аналитические отчеты и графики

## 🏗️ Архитектура

### Основные компоненты

```
📁 tender_history.py
├── 📊 TenderPosition - Позиция тендера
├── 📈 HistoricalTender - Исторический тендер
├── 🔍 TenderHistoryAnalyzer - Основной анализатор
│   ├── extract_tender_positions() - Извлечение позиций
│   ├── generate_search_queries() - Генерация запросов
│   ├── search_similar_tenders() - Поиск похожих тендеров
│   ├── extract_tender_details() - Извлечение деталей
│   ├── analyze_price_dynamics() - Анализ динамики цен
│   ├── generate_price_chart() - Генерация графика
│   └── generate_analysis_report() - Генерация отчета
└── 🎯 analyze_tender_history() - Главный метод
```

## 🔧 Использование

### Базовое использование

```python
from tender_history import TenderHistoryAnalyzer
from damia import damia_client

# Создаем анализатор
analyzer = TenderHistoryAnalyzer(damia_client)

# Анализируем историю тендера
result = await analyzer.analyze_tender_history(tender_data)

if result['success']:
    print(result['report'])  # Текстовый отчет
    # result['chart'] - График в формате BytesIO
    # result['historical_tenders'] - Список исторических тендеров
    # result['price_analysis'] - Анализ цен
else:
    print(f"Ошибка: {result['error']}")
```

### Интеграция в Telegram бот

```python
# В обработчике callback
elif callback_data == "history":
    history_result = await self.history_analyzer.analyze_tender_history(tender_data)
    
    if history_result.get('success'):
        # Отправляем отчет
        await bot.send_message(
            chat_id=user_id,
            text=history_result['report'],
            parse_mode='Markdown'
        )
        
        # Отправляем график
        if history_result.get('chart'):
            await bot.send_photo(
                chat_id=user_id,
                photo=history_result['chart'],
                caption="📊 График динамики цен"
            )
```

## 📊 Алгоритм работы

### 1. Извлечение позиций тендера
```python
positions = await analyzer.extract_tender_positions(tender_data)
```
- Извлекает позиции из разных полей структуры данных
- Поддерживает различные форматы данных
- Создает объекты `TenderPosition`

### 2. Генерация поисковых запросов
```python
queries = await analyzer.generate_search_queries(positions)
```
- Очищает названия от лишних символов
- Создает различные варианты запросов
- Учитывает единицы измерения
- Убирает дубликаты

### 3. Поиск похожих тендеров
```python
similar_tenders = await analyzer.search_similar_tenders(queries, region, max_price, min_price)
```
- Использует DaMIA API для поиска
- Фильтрует по региону и цене (±30%)
- Ограничивает период последними 12 месяцами
- Убирает дубликаты по ID тендера

### 4. Анализ динамики цен
```python
price_analysis = await analyzer.analyze_price_dynamics(historical_tenders, current_price)
```
- Рассчитывает статистику цен
- Сравнивает с текущим тендером
- Определяет тренды

### 5. Генерация отчета и графика
```python
report = await analyzer.generate_analysis_report(historical_tenders, current_tender, price_analysis)
chart = await analyzer.generate_price_chart(historical_tenders, current_price, current_date)
```

## 📋 Структуры данных

### TenderPosition
```python
@dataclass
class TenderPosition:
    name: str                    # Название позиции
    quantity: Optional[float]    # Количество
    unit: Optional[str]          # Единица измерения
    price_per_unit: Optional[float]  # Цена за единицу
    total_price: Optional[float]     # Общая цена
```

### HistoricalTender
```python
@dataclass
class HistoricalTender:
    tender_id: str               # ID тендера
    name: str                    # Название
    region: str                  # Регион
    publication_date: datetime   # Дата публикации
    nmck: float                  # НМЦК
    final_price: Optional[float] # Итоговая цена
    winner_name: Optional[str]   # Победитель
    winner_inn: Optional[str]    # ИНН победителя
    participants_count: Optional[int]  # Количество участников
    subject: str                 # Предмет закупки
    status: str                  # Статус (completed/failed/cancelled)
    price_reduction_percent: Optional[float]  # Снижение цены в %
```

## 📈 Примеры отчетов

### Текстовый отчет
```
📈 История похожих тендеров

🔍 Анализируемый тендер:
📋 Поставка муки пшеничной высшего сорта
💰 НМЦК: 1,000,000 ₽

📊 Похожие тендеры за последние 12 месяцев:

1️⃣ 15.12.2023 — ООО 'МукаПлюс'
   ✅ Победа при 4 участниках
   💰 Цена: 850,000 ₽ (–10.5% от НМЦК)
   📍 Регион: Московская область

2️⃣ 20.10.2023 — ИП Иванов И.И.
   ✅ Победа при 3 участниках
   💰 Цена: 980,000 ₽ (–10.9% от НМЦК)

📉 Анализ цен:
• Средняя цена: 915,000 ₽
• Медианная цена: 915,000 ₽
• Диапазон: 850,000 - 980,000 ₽

📊 Сравнение с текущим тендером:
• От средней: +9.3%
• От медианной: +9.3%

📌 Выводы:
⚠️ Цена выше средней. Рекомендуется проанализировать обоснованность цены.
```

### График
- Точечный график исторических цен
- Линия тренда
- Горизонтальные линии текущей и средней цены
- Подписи осей и легенда

## 🔧 Настройка

### Параметры поиска
```python
search_params = {
    'query': 'мука пшеничная',      # Поисковый запрос
    'date_from': '2023-01-01',      # Дата начала поиска
    'date_to': '2024-01-01',        # Дата окончания поиска
    'region': 'Московская область', # Регион (опционально)
    'limit': 50                     # Лимит результатов
}
```

### Фильтрация по цене
```python
# Текущая цена: 1,000,000 ₽
max_price = current_price * 1.3  # До 1,300,000 ₽
min_price = current_price * 0.7  # От 700,000 ₽
```

## 🧪 Тестирование

Запуск тестов:
```bash
python test_tender_history.py
```

Тесты покрывают:
- ✅ Извлечение позиций тендера
- ✅ Генерация поисковых запросов
- ✅ Создание исторических данных
- ✅ Анализ динамики цен
- ✅ Генерация отчетов
- ✅ Создание графиков

## 📦 Зависимости

```txt
numpy==1.24.3
matplotlib==3.7.2
python-dateutil==2.8.2
```

## 🚀 Интеграция в бот

### Добавление кнопки
```python
keyboard = [
    [InlineKeyboardButton("📈 История тендеров", callback_data="history")]
]
```

### Обработчик
```python
elif callback_data == "history":
    history_result = await self.history_analyzer.analyze_tender_history(tender_data)
    # Отправка результатов пользователю
```

## 📊 Возможности расширения

### Планируемые улучшения
- 🧠 GPT-эмбеддинги для более точного поиска
- 📊 Дополнительные типы графиков
- 🔍 Фильтрация по отраслям
- 📈 Прогнозирование цен
- 💾 Кэширование результатов
- 📋 Экспорт в Excel/PDF

### Кастомизация
- Настройка периодов поиска
- Изменение алгоритмов фильтрации
- Добавление новых типов анализа
- Интеграция с другими API 