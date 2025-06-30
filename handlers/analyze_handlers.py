from analyzer import analyzer
from tenderguru_api import TenderGuruAPI, get_tender_by_number
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from keyboards import analyze_keyboard, back_keyboard, main_menu_keyboard
from utils.validators import extract_tender_info_from_url
from config import TENDERGURU_API_CODE
from navigation_utils import handle_navigation_buttons
from company_profile import build_company_profile

async def analyze_tender_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, bot_instance=None):
    message = update.message or (update.callback_query and update.callback_query.message)
    if not message:
        return
    text = getattr(message, 'text', None)
    if not text:
        await message.reply_text("❌ Введите номер тендера или ссылку.", reply_markup=None)
        return
    text = text.strip()
    tender_info = extract_tender_info_from_url(text)
    tender_number = tender_info['reg_number'] if tender_info and 'reg_number' in tender_info else None
    platform_code = tender_info['source'] if tender_info and 'source' in tender_info else None
    if not tender_number:
        error_msg = """❌ **Не удалось извлечь номер тендера из сообщения или ссылки.**

💡 **Примеры корректных ссылок:**

🏦 **Сбербанк-АСТ:**
`https://www.sberbank-ast.ru/purchaseList/procedureView.html?PurchaseId=123456789`

🏛️ **Росэлторг:**
`https://www.roseltorg.ru/procedure/notice/view?noticeId=987654321`

💼 **B2B-Center:**
`https://www.b2b-center.ru/tender/5555555`

📊 **РТС-тендер:**
`https://www.rts-tender.ru/tender/4444444`

🇷🇺 **Госзакупки:**
`https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0123456789012345678`

🔧 **Или просто отправьте номер тендера:** `123456789`"""
        await message.reply_text(error_msg, parse_mode="Markdown", reply_markup=back_keyboard)
        return
    context.user_data['last_tender_number'] = tender_number
    context.user_data['last_platform_code'] = platform_code
    await message.reply_text("🔍 Ищу тендер по номеру...")
    try:
        tender_data = get_tender_by_number(tender_number, platform_code)
    except Exception as e:
        await message.reply_text(f"❌ Ошибка обращения к TenderGuru API: {e}")
        return
    if not tender_data or 'error' in tender_data or not tender_data.get('results'):
        if platform_code:
            await message.reply_text(f"❌ Тендер не найден по номеру и площадке ({platform_code}). Проверьте корректность ссылки или попробуйте позже.")
        else:
            await message.reply_text(f"❌ Не удалось найти тендер с номером {tender_number}.")
        return
    context.user_data['last_tender_data'] = tender_data
    tender = tender_data['results'][0] if isinstance(tender_data['results'], list) else tender_data['results']
    
    # Получаем данные тендера
    name = tender.get('TorgiName') or tender.get('ContractName') or tender.get('name', '—')
    customer = tender.get('Customer', '—')
    price = tender.get('Price', '—')
    etp = tender.get('ETP', '—')
    end_time = tender.get('EndTime', '—')
    
    # Определяем площадку для отображения
    source_labels = {
        'sberbank-ast': '🏦 Сбербанк-АСТ',
        'roseltorg': '🏛️ Росэлторг',
        'b2b-center': '💼 B2B-Center',
        'etp-ets': '⚡ ETP-ETS',
        'gazneftetrade': '⛽ ГазНефтеТрейд',
        'zakupki.gov.ru': '🇷🇺 Госзакупки',
        'rts-tender': '📊 РТС-тендер',
        'fabrikant': '🏭 Фабрикант',
        'tektorg': '🔧 Текторг'
    }
    source_label = source_labels.get(platform_code, f'📍 {etp}')
    
    # Форматируем цену
    if isinstance(price, (int, float)) and price > 0:
        formatted_price = f"{price:,.0f} ₽"
    else:
        formatted_price = str(price)
    
    # Форматируем дату
    if end_time and end_time != '—':
        try:
            # Пытаемся парсить дату
            from datetime import datetime
            if isinstance(end_time, str):
                # Убираем лишние символы и парсим
                clean_date = end_time.split('T')[0] if 'T' in end_time else end_time
                parsed_date = datetime.strptime(clean_date, '%Y-%m-%d')
                formatted_date = parsed_date.strftime('%d.%m.%Y')
            else:
                formatted_date = str(end_time)
        except:
            formatted_date = str(end_time)
    else:
        formatted_date = '—'
    
    # Создаем красивое сообщение
    msg = f"""📄 **Тендер найдён!**

🏷️ **Название:** {name}
🏢 **Заказчик:** {customer}
💰 **НМЦК:** {formatted_price}
📅 **Приём заявок до:** {formatted_date}
{source_label}

🔍 **Номер тендера:** `{tender_number}`"""
    
    keyboard = [[
        InlineKeyboardButton("📥 Скачать документацию", callback_data="download_docs"),
        InlineKeyboardButton("🧠 Анализировать ТЗ", callback_data="analyze_tz")
    ],[
        InlineKeyboardButton("🦾 Проверить заказчика", callback_data="check_customer"),
        InlineKeyboardButton("📊 История похожих", callback_data="similar_history")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
    # Обработка кнопок навигации
    if bot_instance:
        if handle_navigation_buttons(update, main_menu_keyboard, bot_instance):
            return
    # Обработка кнопок 'Назад' и 'В главное меню'
    # ... удалено ... 

async def handle_tender_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    data = query.data if query else None
    tender_number = context.user_data.get('last_tender_number')
    tender_data = context.user_data.get('last_tender_data')
    if not tender_number or not tender_data or not tender_data.get('results'):
        await query.answer()
        await query.edit_message_text("❌ Не удалось определить номер тендера. Пожалуйста, начните с поиска тендера заново.")
        return
    results = tender_data.get('results')
    tender = results[0] if isinstance(results, list) and results else results if results else None
    if not tender:
        await query.answer()
        await query.edit_message_text("❌ Нет данных по тендеру.")
        return
    if isinstance(tender, dict):
        get = tender.get
    else:
        def get(key, default=None):
            return default
    if data == "download_docs":
        await query.answer()
        docs_link = get('TorgLink') or get('docs_link')
        if docs_link:
            await query.edit_message_text(f"📥 Документация: [Скачать]({docs_link})", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Документация не найдена.")
    elif data == "analyze_tz":
        await query.answer()
        try:
            analyze_func = getattr(analyzer, 'analyze_tender_text', None)
            if analyze_func and callable(analyze_func):
                text = get('TorgiName', '') + '\n' + (get('Info', '') or '')
                analysis = analyze_func(text)
                if hasattr(analysis, '__await__'):
                    analysis = await analysis
            else:
                analysis = "(Анализатор не реализован)"
        except Exception as e:
            analysis = f"Ошибка анализа: {e}"
        await query.edit_message_text(f"🧠 Анализ ТЗ:\n{analysis}")
    elif data == "check_customer":
        await query.answer()
        customer = get('Customer', '—')
        customer_inn = get('CustomerInn', '—')
        try:
            profile = await build_company_profile(customer_inn)
        except Exception as e:
            profile = f"Ошибка получения профиля: {e}"
        await query.edit_message_text(f"🦾 Заказчик: {customer}\nИНН: {customer_inn}\nПрофиль:\n{profile}")
    elif data == "similar_history":
        await query.answer()
        try:
            api = TenderGuruAPI(TENDERGURU_API_CODE)
            kwords = get('TorgiName') or get('ContractName') or ''
            similar = api.get_tenders_by_keywords(kwords)
            tenders = similar.get('results', [])
            msg = '\n'.join([f"• {t.get('TorgiName', t.get('ContractName', '—'))} | {t.get('Price', '—')} ₽ | {t.get('EndTime', '—')}" for t in tenders[:5] if isinstance(t, dict)])
        except Exception as e:
            msg = f"Ошибка поиска похожих: {e}"
        await query.edit_message_text(f"📊 Похожие тендеры:\n{msg if msg else 'Не найдено.'}")
    else:
        await query.answer()
        await query.edit_message_text("Неизвестная команда.")

# ... существующий код ...
# В setup_handlers или bot.py добавить:
# application.add_handler(CallbackQueryHandler(handle_tender_card_callback, pattern="^(download_docs|analyze_tz|check_customer|similar_history)$")) 