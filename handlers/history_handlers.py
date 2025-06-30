# Обработчики истории закупок
from tenderguru_api import TenderGuruAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from keyboards import history_keyboard, back_keyboard, main_menu_keyboard
from config import TENDERGURU_API_CODE
from navigation_utils import handle_navigation_buttons
from utils.validators import extract_tender_info_from_url
from handlers.analyze_handlers import analyze_tender_handler
import logging

# TODO: реализовать обработчики истории закупок, интеграцию с FSM и UX 

logger = logging.getLogger(__name__)

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
    logger.info(f"[history_handler] Получаю историю по запросу: {text}")
    await message.reply_text("⏳ Получаю историю закупок...")
    # Обработка кнопок навигации
    if handle_navigation_buttons(update, context.user_data, main_menu_keyboard):
        logger.info("[history_handler] Навигационная кнопка, выход")
        return
    # Определяем, что это — ИНН или ключевые слова
    if text.isdigit() and len(text) in [10, 12]:
        # Поиск по ИНН (контракты победителя)
        result = api.get_winners_by_inn(text)
        logger.info(f"[history_handler] API get_winners_by_inn({text}) вернул: {result}")
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
        logger.info(f"[history_handler] API get_tenders_by_keywords({text}) вернул: {result}")
        tenders = result.get('results', [])
        if not tenders:
            await message.reply_text("❌ Не найдено тендеров по ключевым словам.", reply_markup=back_keyboard)
            return
        for t in tenders[:5]:
            reg_number = t.get('regNumber') or t.get('number') or t.get('id') or ''
            platform_code = t.get('ETP') or t.get('platform') or ''
            name = t.get('name', t.get('ContractName', ''))
            price = t.get('price', t.get('Price', ''))
            date = t.get('date', t.get('Date', ''))
            msg = f"— {name} | {price} руб. | {date}"
            logger.info(f"[history_handler] tender: reg_number={reg_number}, platform_code={platform_code}, name={name}")
            if reg_number:
                callback_data = f"analyze_found_tender:{reg_number}:{platform_code}"
                logger.info(f"[history_handler] Кнопка Анализировать: callback_data={callback_data}")
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("📄 Анализировать", callback_data=callback_data)]
                ])
            else:
                keyboard = None
            await message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)

async def analyze_found_tender_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return
    logger.info(f"[analyze_found_tender_callback] Получен callback: {query.data}")
    # callback_data: analyze_found_tender:<reg_number>:<platform_code>
    parts = query.data.split(":", 2)
    if len(parts) < 3 or not parts[1]:
        await query.answer()
        await query.edit_message_text("❌ Ошибка: не удалось определить номер тендера.")
        logger.warning(f"[analyze_found_tender_callback] Ошибка парсинга callback_data: {query.data}")
        return
    reg_number = parts[1]
    platform_code = parts[2] if len(parts) > 2 and parts[2] else None
    context.user_data['last_tender_number'] = reg_number
    context.user_data['last_platform_code'] = platform_code
    logger.info(f"[analyze_found_tender_callback] Сохраняем в context.user_data: reg_number={reg_number}, platform_code={platform_code}")
    await query.answer()
    await analyze_tender_handler(update, context, bot_instance=None)

# Для регистрации callback-обработчика:
# application.add_handler(CallbackQueryHandler(analyze_found_tender_callback, pattern=r"^analyze_found_tender:")) 