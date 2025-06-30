"""
Обработчики callback'ов для TenderBot
"""
import logging
import os
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from downloader import downloader
from common_utils import validate_user_session, handle_session_error
from utils.validators import extract_tender_number
from navigation_utils import handle_navigation_buttons

logger = logging.getLogger(__name__)

class CallbackHandlers:
    def __init__(self, bot_instance):
        self.bot = bot_instance
    
    async def handle_products(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Обработка кнопки 'Товарные позиции'"""
        user_id = query.from_user.id
        valid, session = validate_user_session(user_id, self.bot.user_sessions, 'ready_for_analysis')
        if not valid:
            await handle_session_error(query)
            return
        
        tender_data = session['tender_data']
        sent = await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Загрузка товарных позиций..."
        )
        await self.bot._send_products_list_to_chat(
            context.bot, query.message.chat_id, tender_data, page=0, message_id=sent.message_id
        )
    
    async def handle_documents(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Обработка кнопки 'Документы'"""
        user_id = query.from_user.id
        valid, session = validate_user_session(user_id, self.bot.user_sessions, 'ready_for_analysis')
        if not valid:
            await handle_session_error(query)
            return
        
        tender_data = session['tender_data']
        reg_number = extract_tender_number(str(tender_data))
        if not reg_number:
            await query.edit_message_text("❌ Не удалось извлечь номер тендера.")
            return
        
        await self.bot._send_documents_list_with_download(
            context.bot, query.message.chat_id, tender_data, reg_number, page=0
        )
    
    async def handle_detailed_info(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Обработка кнопки 'Подробная информация'"""
        user_id = query.from_user.id
        valid, session = validate_user_session(user_id, self.bot.user_sessions, 'ready_for_analysis')
        if not valid:
            await handle_session_error(query)
            return
        
        tender_data = session['tender_data']
        await self.bot._send_detailed_info_to_chat(
            context.bot, query.message.chat_id, tender_data
        )
    
    async def handle_analyze(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Обработка кнопки 'Детальный анализ'"""
        user_id = query.from_user.id
        valid, session = validate_user_session(user_id, self.bot.user_sessions, 'ready_for_analysis')
        if not valid:
            await handle_session_error(query)
            return
        
        tender_data = session['tender_data']
        await query.edit_message_text("🤖 Начинаю анализ документов...")
        
        try:
            # Скачиваем документы
            reg_number = extract_tender_number(str(tender_data))
            if not reg_number:
                await query.edit_message_text("❌ Не удалось извлечь номер тендера для скачивания документов.")
                return
            
            files = await downloader.download_documents(tender_data, reg_number)
            if not files or files.get('success', 0) == 0:
                await query.edit_message_text("❌ Не удалось скачать документы для анализа.")
                return
            
            session['files'] = files.get('files', [])
            
            # Анализируем документы
            analysis_result = await self.bot._analyze_documents(
                tender_data, 
                files.get('files', []), 
                update=query, 
                chat_id=query.message.chat_id, 
                bot=context.bot
            )
            
            if analysis_result:
                await self.bot._send_analysis_to_chat(context.bot, query.message.chat_id, analysis_result)
                session['status'] = 'completed'
            else:
                await query.edit_message_text("❌ Не удалось проанализировать документы.")
                
        except Exception as e:
            logger.error(f"[bot] Ошибка при анализе: {e}")
            await query.edit_message_text(f"❌ Произошла ошибка при анализе: {str(e)}")
    
    async def handle_products_page(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Обработка пагинации товарных позиций"""
        user_id = query.from_user.id
        try:
            page = int(query.data.split("_")[2])
        except Exception:
            page = 0
        
        valid, session = validate_user_session(user_id, self.bot.user_sessions, 'ready_for_analysis')
        if not valid:
            await handle_session_error(query)
            return
        
        tender_data = session['tender_data']
        logger.info(f"[bot] Навигация по товарам: page={page}, message_id={query.message.message_id}")
        await self.bot._send_products_list_to_chat(
            context.bot, query.message.chat_id, tender_data, page=page, message_id=query.message.message_id
        )
    
    async def handle_documents_page(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Обработка пагинации документов"""
        user_id = query.from_user.id
        page = int(query.data.split('_')[-1])
        
        valid, session = validate_user_session(user_id, self.bot.user_sessions, 'ready_for_analysis')
        if not valid:
            await handle_session_error(query)
            return
        
        tender_data = session['tender_data']
        reg_number = extract_tender_number(str(tender_data))
        if not reg_number:
            await query.edit_message_text("❌ Не удалось извлечь номер тендера.")
            return
        
        await self.bot._update_documents_message(
            context.bot, 
            query.message.chat_id, 
            query.message.message_id, 
            tender_data, 
            reg_number, 
            page
        )
    
    async def handle_download(self, query, context: ContextTypes.DEFAULT_TYPE):
        """Обработка скачивания файла"""
        user_id = query.from_user.id
        file_id = query.data.split('_', 1)[1]
        
        valid, session = validate_user_session(user_id, self.bot.user_sessions, 'ready_for_analysis')
        if not valid:
            await handle_session_error(query)
            return
        
        tender_data = session['tender_data']
        reg_number = extract_tender_number(str(tender_data))
        if not reg_number:
            await query.edit_message_text("❌ Не удалось извлечь номер тендера.")
            return
        
        try:
            file_path = downloader.get_file_path(reg_number, file_id)
            if file_path and os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=query.message.chat_id,
                        document=f,
                        filename=os.path.basename(file_path)
                    )
            else:
                await query.edit_message_text("❌ Файл не найден.")
        except Exception as e:
            logger.error(f"[bot] Ошибка при отправке файла: {e}")
            await query.edit_message_text(f"❌ Ошибка при отправке файла: {str(e)}") 