welcome_text = (
    "👋 Добро пожаловать в TenderBot — помощника по госзакупкам\n\n"
    "Выберите, что вы хотите сделать:"
)

analyze_tender_text = (
    "🔍 Пришлите номер тендера или ссылку на него:\n"
    "(например: 0173100004725000020)"
)

analyze_result_text = (
    "✅ Анализ завершён! Вот ключевые параметры:\n"
    "— Товар, количество, упаковка, требования\n\n"
    "Что дальше?"
)

search_tender_text = (
    "🔍 Введите ключевые слова (например: 'цемент', 'стройматериалы')\n\n"
    "Вы также можете настроить фильтры: регион, цена, дата, закон."
)

check_company_text = (
    "Введите ИНН или название компании:\n\n"
    "Бот покажет: название, директор, ОГРН, финансы, риски, участие в тендерах, контакты."
)

analytics_text = (
    "Выберите, что проанализировать:\n\n"
    "🔎 По ключевым словам\n🏆 По победителям\n💰 По изменениям цен\n📍 По региону или заказчику"
)

profile_text = (
    "👤 Ваш статус: Бесплатный / Подписка\n"
    "📅 Осталось: X запросов\n\n"
    "Доступные действия: продлить подписку, оплатить, скачать историю."
)

help_text = (
    "ℹ️ TenderBot — это ИИ-ассистент по госзакупкам.\n\n"
    "Он умеет:\n"
    "✅ Анализировать ТЗ\n"
    "✅ Проверять поставщиков\n"
    "✅ Искать тендеры по всей России\n"
    "✅ Предсказывать победителей и анализировать цены\n\n"
    "По всем вопросам: @ваш_логин"
)

locked_text = (
    "🚫 Вы использовали 3 бесплатных анализа.\n\n"
    "🔓 Подпишитесь, чтобы получить:\n"
    "+ Неограниченные запросы\n"
    "+ Доступ к аналитике победителей\n"
    "+ Выгрузки в Excel\n"
    "+ Поиск поставщиков по базе\n\n"
    "💳 Подписка — 3000₽ в месяц"
)

inn_invalid_text = "❌ Неверный ИНН. Введите 10 или 12 цифр с корректной контрольной суммой.\nПример: 7707083893 или 500100732259."
tender_invalid_text = "❌ Неверный номер тендера или ссылка.\nПример: 0173100004725000020 или https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0173100004725000020"
keywords_invalid_text = "❌ Введите ключевые слова (минимум 2 буквы, не используйте слова 'тендер', 'закупка' и т.п.).\nПример: цемент, стройматериалы, бумага."
success_analyze_text = "✅ Анализ завершён! Хотите проверить поставщика?"
success_supplier_text = "✅ Проверка завершена! Хотите найти тендеры для этой компании?"
success_search_text = "✅ Поиск завершён! Хотите проанализировать найденный тендер?"
suggest_supplier_check_text = "🔎 Проверить поставщика"
suggest_tender_search_text = "🔍 Найти тендеры"
suggest_analyze_text = "📄 Анализировать тендер"
back_to_menu_text = "⬅️ Назад в меню"
success_analytics_text = "✅ Аналитика готова! Хотите скачать отчёт или посмотреть график?"
success_profile_text = "✅ Профиль обновлён! Что сделать дальше?"
success_email_text = "✅ Письмо сгенерировано! Хотите скопировать текст или вернуться к поставщику?"
analytics_invalid_text = "❌ Ошибка в параметрах аналитики. Попробуйте выбрать другой вариант."
profile_invalid_text = "❌ Ошибка в данных профиля. Проверьте ввод."
email_invalid_text = "❌ Не удалось сгенерировать письмо. Попробуйте ещё раз."
tooltip_first_start = "ℹ️ Используйте главное меню для выбора действия. Бот подскажет на каждом шаге!"
tooltip_error_repeat = "💡 Если не получается — проверьте пример выше или вернитесь в меню." 