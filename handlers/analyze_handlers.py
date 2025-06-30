from analyzer import analyzer
from tenderguru_api import TenderGuruAPI, get_tender_by_number
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from keyboards import analyze_keyboard, back_keyboard, main_menu_keyboard
from utils.validators import extract_tender_number_and_platform
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
    tender_number, platform_code = extract_tender_number_and_platform(text)
    if not tender_number:
        await message.reply_text("❌ Не удалось извлечь номер тендера из сообщения или ссылки. Попробуйте ещё раз.", reply_markup=back_keyboard)
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
    name = tender.get('TorgiName') or tender.get('ContractName') or tender.get('name', '—')
    customer = tender.get('Customer', '—')
    price = tender.get('Price', '—')
    etp = tender.get('ETP', '—')
    end_time = tender.get('EndTime', '—')
    msg = f"📄 Тендер: {name}\n🏢 Заказчик: {customer}\n💰 НМЦК: {price} ₽\n📅 Приём заявок до: {end_time}\n📍 Площадка: {etp}"
    keyboard = [[
        InlineKeyboardButton("📥 Скачать документацию", callback_data="download_docs"),
        InlineKeyboardButton("🧠 Анализировать ТЗ", callback_data="analyze_tz")
    ],[
        InlineKeyboardButton("🦾 Проверить заказчика", callback_data="check_customer"),
        InlineKeyboardButton("📊 История похожих", callback_data="similar_history")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(msg, reply_markup=reply_markup)
    # Обработка кнопок навигации
    if bot_instance:
        if handle_navigation_buttons(update, main_menu_keyboard, bot_instance):
            return
    # Обработка кнопок 'Назад' и 'В главное меню'
    # ... удалено ... 

async def handle_tender_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    tender_number = context.user_data.get('last_tender_number')
    tender_data = context.user_data.get('last_tender_data')
    if not tender_number or not tender_data:
        await query.answer()
        await query.edit_message_text("❌ Не удалось определить номер тендера. Пожалуйста, начните с поиска тендера заново.")
        return
    tender = tender_data['results'][0] if isinstance(tender_data['results'], list) else tender_data['results']
    if data == "download_docs":
        await query.answer()
        docs_link = tender.get('TorgLink') or tender.get('docs_link') if tender else None
        if docs_link:
            await query.edit_message_text(f"📥 Документация: [Скачать]({docs_link})", parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Документация не найдена.")
    elif data == "analyze_tz":
        await query.answer()
        if tender:
            try:
                if hasattr(analyzer, 'analyze_tender_text'):
                    analysis = await analyzer.analyze_tender_text(tender.get('TorgiName', '') + '\n' + (tender.get('Info', '') or ''))
                else:
                    analysis = "(Анализатор не реализован)"
            except Exception as e:
                analysis = f"Ошибка анализа: {e}"
            await query.edit_message_text(f"🧠 Анализ ТЗ:\n{analysis}")
        else:
            await query.edit_message_text("❌ Нет данных для анализа ТЗ.")
    elif data == "check_customer":
        await query.answer()
        if tender:
            customer = tender.get('Customer', '—')
            customer_inn = tender.get('CustomerInn', '—')
            try:
                profile = await build_company_profile(customer_inn)
            except Exception as e:
                profile = f"Ошибка получения профиля: {e}"
            await query.edit_message_text(f"🦾 Заказчик: {customer}\nИНН: {customer_inn}\nПрофиль:\n{profile}")
        else:
            await query.edit_message_text("❌ Нет данных о заказчике.")
    elif data == "similar_history":
        await query.answer()
        if tender:
            try:
                api = TenderGuruAPI(TENDERGURU_API_CODE)
                kwords = tender.get('TorgiName') or tender.get('ContractName') or ''
                similar = api.get_tenders_by_keywords(kwords)
                tenders = similar.get('results', [])
                msg = '\n'.join([f"• {t.get('TorgiName', t.get('ContractName', '—'))} | {t.get('Price', '—')} ₽ | {t.get('EndTime', '—')}" for t in tenders[:5]])
            except Exception as e:
                msg = f"Ошибка поиска похожих: {e}"
            await query.edit_message_text(f"📊 Похожие тендеры:\n{msg if msg else 'Не найдено.'}")
        else:
            await query.edit_message_text("❌ Нет данных для поиска похожих.")
    else:
        await query.answer()
        await query.edit_message_text("Неизвестная команда.")

# ... существующий код ...
# В setup_handlers или bot.py добавить:
# application.add_handler(CallbackQueryHandler(handle_tender_card_callback, pattern="^(download_docs|analyze_tz|check_customer|similar_history)$")) 