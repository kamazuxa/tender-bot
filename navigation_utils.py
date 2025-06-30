from telegram import Update

def safe_get_message(update: Update):
    if update.message:
        return update.message
    elif update.callback_query and update.callback_query.message:
        return update.callback_query.message
    return None

def handle_navigation_buttons(update, main_menu_keyboard, bot_instance) -> bool:
    message = safe_get_message(update)
    if not message:
        return False
    text = getattr(message, 'text', None)
    user = getattr(update, 'effective_user', None)
    user_id = getattr(user, 'id', None)
    if not text or not user_id:
        return False
    text = text.strip()
    if text == '🏠 В главное меню':
        if user_id in bot_instance.user_sessions:
            bot_instance.user_sessions[user_id]['state'] = 'MAIN_MENU'
            bot_instance.user_sessions[user_id]['status'] = 'waiting_for_tender'
        message.reply_text(
            "Главное меню:",
            reply_markup=main_menu_keyboard
        )
        return True
    if text == '🔙 Назад':
        if user_id in bot_instance.user_sessions:
            state = bot_instance.user_sessions[user_id].get('state')
            if state and state.startswith('WAIT_'):
                bot_instance.user_sessions[user_id]['state'] = state.replace('WAIT_', '')
            else:
                bot_instance.user_sessions[user_id]['state'] = 'MAIN_MENU'
                bot_instance.user_sessions[user_id]['status'] = 'waiting_for_tender'
        message.reply_text(
            "Вы вернулись назад.",
            reply_markup=main_menu_keyboard
        )
        return True
    return False 