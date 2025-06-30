from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# Константы callback_data
ANALYZE_CB = "analyze_tender"
SEARCH_CB = "search_tenders"
SUPPLIER_CB = "check_company"
ANALYTICS_CB = "view_analytics"
PROFILE_CB = "profile_menu"
HELP_CB = "help_menu"
LOCKED_CB = "buy_subscription"
BACK_CB = "back_to_main"
# Для умного возврата
SUGGEST_SUPPLIER_CB = "suggest_supplier_check"
SUGGEST_SEARCH_CB = "suggest_tender_search"
SUGGEST_ANALYZE_CB = "suggest_analyze"
ANALYTICS_REPORT_CB = "analytics_report"
ANALYTICS_GRAPH_CB = "analytics_graph"
PROFILE_SUB_CB = "profile_subscribe"
PROFILE_NOTIFY_CB = "profile_notify"
EMAIL_COPY_CB = "email_copy"
EMAIL_BACK_SUPPLIER_CB = "email_back_supplier"
HISTORY_REPEAT_CB = "history_repeat"

main_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📄 Анализировать тендер", callback_data=ANALYZE_CB)],
    [InlineKeyboardButton("📦 Найти тендер", callback_data=SEARCH_CB)],
    [InlineKeyboardButton("👤 Проверить поставщика", callback_data=SUPPLIER_CB)],
    [InlineKeyboardButton("📊 Посмотреть аналитику", callback_data=ANALYTICS_CB)],
    [InlineKeyboardButton("⚙️ Мой профиль", callback_data=PROFILE_CB)],
    [InlineKeyboardButton("ℹ️ Помощь", callback_data=HELP_CB)],
])

analyze_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📦 Найти поставщика", callback_data="find_supplier")],
    [InlineKeyboardButton("📊 Кто выигрывал такие тендеры?", callback_data="winner_stats")],
    [InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_main")],
])

search_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📝 Показать 10 свежих тендеров", callback_data="show_tenders")],
    [InlineKeyboardButton("📤 Выгрузить в Excel", callback_data="export_excel")],
    [InlineKeyboardButton("🔔 Подписаться на подборки", callback_data="subscribe_selection")],
    [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")],
])

supplier_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("🧠 Оценить надёжность", callback_data="assess_reliability")],
    [InlineKeyboardButton("📞 Контакты и соцсети", callback_data="show_contacts")],
    [InlineKeyboardButton("📊 История участия в закупках", callback_data="show_tender_history")],
    [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")],
])

analytics_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📈 Показать график или таблицу", callback_data="show_analytics")],
    [InlineKeyboardButton("📝 Скачать отчёт Excel", callback_data="download_analytics_excel")],
    [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")],
])

profile_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("💳 Купить подписку (3000₽)", callback_data="buy_subscription")],
    [InlineKeyboardButton("🔔 Настроить уведомления", callback_data="setup_notifications")],
    [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")],
])

help_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📘 Частые вопросы", callback_data="faq")],
    [InlineKeyboardButton("✍️ Написать в поддержку", callback_data="contact_support")],
    [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_main")],
])

locked_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("💳 Купить подписку", callback_data="buy_subscription")],
    [InlineKeyboardButton("⬅️ Назад в меню", callback_data="back_to_main")],
])

analyze_suggest_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔎 Проверить поставщика", callback_data=SUGGEST_SUPPLIER_CB)],
    [InlineKeyboardButton("⬅️ В меню", callback_data=BACK_CB)],
])
supplier_suggest_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📦 Найти тендеры", callback_data=SUGGEST_SEARCH_CB)],
    [InlineKeyboardButton("⬅️ В меню", callback_data=BACK_CB)],
])
search_suggest_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📄 Анализировать тендер", callback_data=SUGGEST_ANALYZE_CB)],
    [InlineKeyboardButton("⬅️ В меню", callback_data=BACK_CB)],
])

back_to_menu_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("⬅️ Назад в меню", callback_data=BACK_CB)]
])

analytics_suggest_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📈 Посмотреть график", callback_data=ANALYTICS_GRAPH_CB)],
    [InlineKeyboardButton("📝 Скачать отчёт", callback_data=ANALYTICS_REPORT_CB)],
    [InlineKeyboardButton("⬅️ В меню", callback_data=BACK_CB)],
])
profile_suggest_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("💳 Продлить подписку", callback_data=PROFILE_SUB_CB)],
    [InlineKeyboardButton("🔔 Настроить уведомления", callback_data=PROFILE_NOTIFY_CB)],
    [InlineKeyboardButton("⬅️ В меню", callback_data=BACK_CB)],
])
email_suggest_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("📋 Скопировать текст", callback_data=EMAIL_COPY_CB)],
    [InlineKeyboardButton("👤 К поставщику", callback_data=EMAIL_BACK_SUPPLIER_CB)],
    [InlineKeyboardButton("⬅️ В меню", callback_data=BACK_CB)],
])
history_keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔄 Повторить последнее действие", callback_data=HISTORY_REPEAT_CB)],
    [InlineKeyboardButton("⬅️ В меню", callback_data=BACK_CB)],
])

back_keyboard = ReplyKeyboardMarkup([[KeyboardButton('🔙 Назад')]], resize_keyboard=True)
main_menu_keyboard = ReplyKeyboardMarkup([
    [KeyboardButton('📦 Анализ тендера'), KeyboardButton('🦾 Проверка компании')],
    [KeyboardButton('📊 История закупок'), KeyboardButton('💼 Личный кабинет')],
    [KeyboardButton('🏠 В главное меню')]
], resize_keyboard=True) 