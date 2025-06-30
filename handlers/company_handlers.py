# Обработчики проверки компании
from company_profile import build_company_profile
from telegram import Update
from telegram.ext import ContextTypes
from keyboards import supplier_keyboard, back_keyboard, main_menu_keyboard
from utils.validators import is_valid_inn
import asyncio
from utils import handle_navigation_buttons
from bot import bot

# TODO: реализовать обработчики проверки компании, интеграцию с FSM и UX 

async def check_company_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or (update.callback_query and update.callback_query.message)
    if not message:
        return
    text = getattr(message, 'text', None)
    if not text:
        await message.reply_text("❌ Введите ИНН компании.", reply_markup=back_keyboard)
        return
    text = text.strip()
    if not is_valid_inn(text):
        await message.reply_text("❌ Введите корректный ИНН (10 или 12 цифр).", reply_markup=back_keyboard)
        return
    inn = text
    await message.reply_text("⏳ Получаю профиль компании...", reply_markup=back_keyboard)
    loop = asyncio.get_event_loop()
    profile = await loop.run_in_executor(None, build_company_profile, inn)
    await message.reply_text(profile, parse_mode="Markdown", reply_markup=main_menu_keyboard)
    # Обработка кнопок навигации
    if handle_navigation_buttons(update, bot.user_sessions, main_menu_keyboard):
        return
    # Обработка кнопок 'Назад' и 'В главное меню'
    # ... удалено ... 