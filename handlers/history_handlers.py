# Обработчики истории закупок
from tenderguru_api import TenderGuruAPI
from telegram import Update
from telegram.ext import ContextTypes
from keyboards import history_keyboard, back_keyboard, main_menu_keyboard
from config import TENDERGURU_API_CODE
from navigation_utils import handle_navigation_buttons
from bot import bot

# TODO: реализовать обработчики истории закупок, интеграцию с FSM и UX 

async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or (update.callback_query and update.callback_query.message)
    if not message:
        return
    text = getattr(message, 'text', None)
    if not text:
        await message.reply_text("❌ Введите ключевые слова или ИНН.", reply_markup=back_keyboard)
        return
    text = text.strip()
    api = TenderGuruAPI(TENDERGURU_API_CODE)
    await message.reply_text("⏳ Получаю историю закупок...")
    # Обработка кнопок навигации
    if handle_navigation_buttons(update, bot.user_sessions, main_menu_keyboard):
        return
    # Определяем, что это — ИНН или ключевые слова
    if text.isdigit() and len(text) in [10, 12]:
        # Поиск по ИНН (контракты победителя)
        result = api.get_winners_by_inn(text)
        contracts = result.get('results', [])
        if not contracts:
            await message.reply_text("❌ Не найдено контрактов по ИНН.", reply_markup=back_keyboard)
            return
        summary = f"Контракты победителя по ИНН {text} (первые 5):\n"
        for c in contracts[:5]:
            summary += f"— {c.get('ContractName', c.get('name', ''))} | {c.get('Price', c.get('price', ''))} руб. | {c.get('Date', c.get('date', ''))}\n"
        await message.reply_text(summary, parse_mode="Markdown", reply_markup=main_menu_keyboard)
    else:
        # Поиск по ключевым словам (тендеры)
        result = api.get_tenders_by_keywords(text)
        tenders = result.get('results', [])
        if not tenders:
            await message.reply_text("❌ Не найдено тендеров по ключевым словам.", reply_markup=back_keyboard)
            return
        summary = f"Тендеры по запросу '{text}' (первые 5):\n"
        for t in tenders[:5]:
            summary += f"— {t.get('name', t.get('ContractName', ''))} | {t.get('price', t.get('Price', ''))} руб. | {t.get('date', t.get('Date', ''))}\n"
        await message.reply_text(summary, parse_mode="Markdown", reply_markup=main_menu_keyboard) 