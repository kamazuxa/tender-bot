# Админ панель TenderBot

## 👨‍💼 Обзор

Админ панель доступна только для пользователя с username `hoproqr`. Она предоставляет полный контроль над системой и мониторинг всех процессов.

## 🔐 Доступ

Админ панель автоматически появляется в личном кабинете для пользователя:
- **Username:** `hoproqr`
- **Уровень доступа:** Супер-администратор

## 📊 Основные разделы

### 👥 Управление пользователями
- **Общая статистика:** Количество пользователей, активных сессий, завершенных анализов
- **Последние активные пользователи:** Список последних 5 активных пользователей
- **Подробная статистика:** Детальная информация по каждому пользователю
- **Поиск пользователя:** Поиск по ID пользователя

### 📊 Статистика системы
- **Пользователи:** Общая статистика по пользователям
- **Запросы:** Количество запросов и среднее на пользователя
- **Активность:** Активные сессии и ожидающие ввода
- **Периоды:** Статистика по дням, неделям, месяцам

### ⚙️ Настройки системы
- **Текущие параметры:** Лимиты запросов, размеры файлов, время кэша
- **API статус:** Статус всех подключенных API
- **Системные параметры:** Логирование, VPN, автоочистка

### 📋 Системные логи
- **Последние записи:** Последние 5 записей из логов
- **Полные логи:** Доступ ко всем логам системы
- **Поиск по логам:** Фильтрация логов по типам и времени
- **Очистка логов:** Управление размером лог-файлов

## 🔧 Функции управления

### Изменение лимитов
- Дневной лимит запросов
- Максимальный размер файлов
- Время жизни кэша
- Количество попыток API

### Перезапуск API
- Перезапуск всех подключенных API
- Проверка доступности сервисов
- Обновление статуса подключений

### Очистка кэша
- Очистка кэша анализа
- Очистка временных файлов
- Освобождение памяти

### Управление логами
- Просмотр всех логов
- Поиск по ключевым словам
- Фильтрация по типам (INFO, WARNING, ERROR, DEBUG)
- Очистка старых логов

## 📈 Мониторинг

### API статус
- ✅ DaMIA API - Активен
- ✅ OpenAI API - Активен
- ✅ SerpAPI - Активен
- ✅ FNS API - Активен
- ✅ Arbitr API - Активен
- ✅ Scoring API - Активен
- ✅ FSSP API - Активен

### Системные параметры
- Логирование: Включено
- VPN для OpenAI: Настроен
- Автоочистка файлов: Включена

## 🚨 Безопасность

### Ограничения доступа
- Доступ только для `hoproqr`
- Проверка username при каждом запросе
- Логирование всех действий администратора

### Защита данных
- Шифрование чувствительной информации
- Ограничение доступа к пользовательским данным
- Автоматическое резервное копирование

## 📋 Логирование действий

Все действия в админ панели записываются в лог с пометкой `[ADMIN]`:
```
2024-01-15 10:30:15 - [ADMIN] hoproqr просмотрел статистику пользователей
2024-01-15 10:31:20 - [ADMIN] hoproqr очистил кэш системы
2024-01-15 10:32:05 - [ADMIN] hoproqr изменил дневной лимит на 200
```

## 🔄 Автоматические процессы

### Мониторинг системы
- Проверка доступности API каждые 5 минут
- Автоматическая очистка старых файлов
- Мониторинг использования памяти

### Уведомления
- Уведомления о критических ошибках
- Предупреждения о превышении лимитов
- Информация о новых пользователях

## 📞 Поддержка

При возникновении проблем с админ панелью:
- Проверьте логи системы
- Убедитесь в правильности username
- Обратитесь к разработчику

## 🔮 Планы развития

### Краткосрочные планы
- [ ] Веб-интерфейс админ панели
- [ ] Уведомления в Telegram
- [ ] Экспорт статистики в Excel
- [ ] Автоматические отчеты

### Долгосрочные планы
- [ ] Мультиуровневая система доступа
- [ ] Интеграция с внешними системами мониторинга
- [ ] Машинное обучение для предсказания проблем
- [ ] Автоматическое масштабирование ресурсов 