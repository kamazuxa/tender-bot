from analyzer import analyzer
from tenderguru_api import TenderGuruAPI
from telegram import Update
from telegram.ext import ContextTypes
from keyboards import analyze_keyboard, back_keyboard, main_menu_keyboard
from utils.validators import extract_tender_number
from config import TENDERGURU_API_CODE
from navigation_utils import handle_navigation_buttons
from bot import bot

async def analyze_tender_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or (update.callback_query and update.callback_query.message)
    if not message:
        return
    text = getattr(message, 'text', None)
    if not text:
        await message.reply_text("❌ Введите номер тендера или ссылку.", reply_markup=back_keyboard)
        return
    text = text.strip()
    tender_number = extract_tender_number(text)
    if not tender_number:
        await message.reply_text("❌ Введите корректный номер тендера или ссылку.", reply_markup=back_keyboard)
        return
    await message.reply_text("🔍 Ищу тендер по номеру...")
    # Интеграция с TenderGuruAPI
    api = TenderGuruAPI(TENDERGURU_API_CODE)
    tender_data = None
    try:
        # TenderGuru не имеет прямого поиска по номеру, ищем по ключевым словам (номер)
        result = api.get_tenders_by_keywords(tender_number)
        tenders = result.get('results', [])
        if not tenders:
            await message.reply_text("❌ Тендер не найден по номеру.", reply_markup=back_keyboard)
            return
        tender_data = tenders[0]  # Берём первый найденный
    except Exception as e:
        await message.reply_text(f"❌ Ошибка поиска тендера: {e}", reply_markup=back_keyboard)
        return
    files = []
    await message.reply_text("🤖 Анализирую тендер с помощью GPT...", reply_markup=back_keyboard)
    result = await analyzer.analyze_tender_documents(tender_data, files)
    summary = result.get("overall_analysis", {}).get("summary", "Анализ недоступен")
    await message.reply_text(summary, parse_mode="Markdown", reply_markup=main_menu_keyboard)
    # Обработка кнопок навигации
    if handle_navigation_buttons(update, bot.user_sessions, main_menu_keyboard):
        return
    # Обработка кнопок 'Назад' и 'В главное меню'
    # ... удалено ... 