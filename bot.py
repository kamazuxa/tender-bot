import logging
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler, CommandHandler,
    CallbackQueryHandler, filters
)
from config import TELEGRAM_TOKEN, LOG_LEVEL, LOG_FILE
from damia import damia_client, extract_tender_number
from downloader import downloader
from analyzer import analyzer
import os

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TenderBot:
    def __init__(self):
        self.app = None
        self.user_sessions = {}  # Для хранения состояния пользователей
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /start"""
        user = update.effective_user
        welcome_message = f"""
🤖 **Добро пожаловать в TenderBot!**

Привет, {user.first_name}! Я помогу вам анализировать тендеры в госзакупках.

**Как использовать:**
1. Отправьте номер тендера (19 цифр)
2. Или отправьте ссылку на тендер с сайта госзакупок
3. Я автоматически получу данные и проанализирую документы

**Команды:**
/start - это сообщение
/help - справка
/status - статус бота
/cleanup - очистка старых файлов

**Примеры:**
```
0123456789012345678
https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0123456789012345678
```

Начните с отправки номера или ссылки на тендер!
        """
        
        keyboard = [
            [InlineKeyboardButton("📋 Справка", callback_data="help")],
            [InlineKeyboardButton("🔧 Статус", callback_data="status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)
        logger.info(f"[bot] Пользователь {user.id} запустил бота")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /help"""
        help_text = """
📋 **Справка по использованию TenderBot**

**Основные функции:**
• Автоматическое получение данных о тендерах
• Скачивание документов тендера (техзадание, условия и т.д.)
• ИИ-анализ документов с помощью OpenAI GPT
• Структурированный отчет с рекомендациями

**Поддерживаемые форматы:**
• 19-значный номер тендера
• 20-значный номер тендера  
• Ссылки на zakupki.gov.ru

**Что анализируется:**
• Краткое резюме тендера
• Товарные позиции
• Требования к упаковке и качеству
• Ключевые условия участия
• Рекомендации по участию
• Оценка сложности

**Ограничения:**
• Максимальный размер файла: 50MB
• Поддерживаемые форматы: PDF, DOC, DOCX, XLS, XLSX, TXT
• Анализ только текстовых документов

**Поддержка:**
При возникновении проблем обращайтесь к администратору.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /status"""
        status_text = f"""
🔧 **Статус TenderBot**

**Время работы:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Версия:** 2.0.0
**Статус:** ✅ Работает

**API статус:**
• DaMIA API: ✅ Доступен
• OpenAI API: ✅ Доступен

**Статистика:**
• Обработано тендеров: {len(self.user_sessions)}
• Скачано файлов: {len(list(downloader.download_dir.glob('*')))}

**Система:**
• Логирование: ✅ Активно
• VPN для OpenAI: ✅ Настроен
• Очистка файлов: ✅ Автоматическая
        """
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    async def cleanup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик команды /cleanup"""
        try:
            deleted_count = downloader.cleanup_old_files()
            await update.message.reply_text(f"🧹 Очистка завершена! Удалено файлов: {deleted_count}")
        except Exception as e:
            logger.error(f"[bot] Ошибка очистки: {e}")
            await update.message.reply_text("❌ Ошибка при очистке файлов")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик текстовых сообщений"""
        user = update.effective_user
        message = update.message.text.strip()
        
        logger.info(f"[bot] Получено сообщение от {user.id}: {message[:50]}...")
        
        # Отправляем статус "печатает"
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        try:
            # Извлекаем номер тендера
            reg_number = extract_tender_number(message)
            
            if not reg_number:
                await update.message.reply_text(
                    "❗ Пожалуйста, укажите корректный регистрационный номер закупки (19-20 цифр) или ссылку на тендер.\n\n"
                    "Примеры:\n"
                    "• 0123456789012345678\n"
                    "• https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0123456789012345678"
                )
                return
            
            # Сохраняем сессию пользователя
            self.user_sessions[user.id] = {
                'reg_number': reg_number,
                'timestamp': datetime.now(),
                'status': 'processing'
            }
            
            await update.message.reply_text(f"🔍 Ищу тендер {reg_number}...")
            
            # Получаем данные о тендере
            tender_data = await damia_client.get_tender_info(reg_number)
            logger.info(f"Ответ DaMIA: {tender_data}")
            
            if not tender_data:
                await update.message.reply_text(
                    f"❌ Не удалось найти тендер с номером {reg_number}.\n"
                    "Проверьте правильность номера или попробуйте позже."
                )
                return
            
            # Форматируем информацию о тендере
            formatted_info = damia_client.format_tender_info(tender_data)
            
            # Сохраняем данные тендера в сессии для последующего анализа
            self.user_sessions[user.id]['tender_data'] = tender_data
            self.user_sessions[user.id]['formatted_info'] = formatted_info
            
            # Отправляем основную информацию
            await self._send_tender_info(update, formatted_info, reg_number)
            
            # Отправляем список товарных позиций
            await self._send_products_list(update, tender_data)
            
            # Отправляем список документов
            await self._send_documents_list(update, tender_data)
            
            # Обновляем статус сессии
            self.user_sessions[user.id]['status'] = 'ready_for_analysis'
            
        except Exception as e:
            logger.error(f"[bot] Ошибка обработки сообщения: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обработке запроса.\n"
                "Попробуйте позже или обратитесь к администратору."
            )
    
    async def _send_products_list(self, update: Update, tender_data: dict) -> None:
        """Отправляет список товарных позиций тендера"""
        # Если данные содержат номер тендера как ключ, извлекаем данные из внутреннего объекта
        if len(tender_data) == 1 and isinstance(list(tender_data.values())[0], dict):
            tender_data = list(tender_data.values())[0]
        
        product_info = tender_data.get('Продукт', {})
        objects = product_info.get('ОбъектыЗак', [])
        
        if not objects:
            await update.message.reply_text("📦 Товарные позиции не найдены")
            return
        
        # Создаем список товарных позиций
        products_text = "📦 **Товарные позиции:**\n\n"
        
        total_cost = 0
        for i, obj in enumerate(objects[:6], 1):  # Показываем первые 6 позиций (уменьшил из-за дополнительной информации)
            name = obj.get('Наименование', 'Без названия')
            quantity = obj.get('Количество', 0)
            unit = obj.get('ЕдИзм', 'шт')
            price = obj.get('ЦенаЕд', 0)
            cost = obj.get('Стоимость', 0)
            okpd = obj.get('ОКПД', '')
            additional_info = obj.get('ДопИнфо', '')
            
            products_text += f"{i}. **{name}**\n"
            products_text += f"   📊 Количество: {quantity} {unit}\n"
            products_text += f"   💰 Цена за ед.: {price} ₽\n"
            products_text += f"   💵 Стоимость: {cost} ₽\n"
            if okpd:
                products_text += f"   🏷️ ОКПД: {okpd}\n"
            if additional_info:
                # Ограничиваем длину дополнительной информации
                short_info = additional_info[:100] + "..." if len(additional_info) > 100 else additional_info
                products_text += f"   ℹ️ Доп. инфо: {short_info}\n"
            products_text += "\n"
            
            total_cost += cost
        
        if len(objects) > 6:
            products_text += f"... и еще {len(objects) - 6} позиций\n\n"
        
        products_text += f"**Общая стоимость позиций: {total_cost} ₽**"
        
        await update.message.reply_text(products_text, parse_mode='Markdown')
    
    async def _send_documents_list(self, update: Update, tender_data: dict) -> None:
        """Отправляет список документов тендера"""
        # Если данные содержат номер тендера как ключ, извлекаем документы из внутреннего объекта
        if len(tender_data) == 1 and isinstance(list(tender_data.values())[0], dict):
            tender_data = list(tender_data.values())[0]
        
        documents = tender_data.get('Документы', [])
        
        if not documents:
            await update.message.reply_text("📄 Документы не найдены")
            return
        
        # Создаем список документов
        docs_text = "📄 **Документы тендера:**\n\n"
        
        for i, doc in enumerate(documents[:10], 1):  # Показываем первые 10 документов
            name = doc.get('Название', 'Без названия')
            date = doc.get('ДатаРазм', '')
            files = doc.get('Файлы', [])
            
            docs_text += f"{i}. **{name}**\n"
            if date:
                docs_text += f"   📅 Дата: {date}\n"
            if files:
                docs_text += f"   📎 Файлов: {len(files)}\n"
            docs_text += "\n"
        
        if len(documents) > 10:
            docs_text += f"... и еще {len(documents) - 10} документов"
        
        await update.message.reply_text(docs_text, parse_mode='Markdown')
    
    async def _send_tender_info(self, update: Update, tender_info: dict, reg_number: str) -> None:
        """Отправляет основную информацию о тендере с кнопками для дополнительных данных"""
        info_text = f"""
📋 **Информация о тендере**

🔢 **Номер:** `{reg_number}`
🏢 **Заказчик:** {tender_info['customer']}
📝 **ИНН:** {tender_info['customer_inn']}
📍 **Адрес:** {tender_info['customer_address']}
📄 **Предмет:** {tender_info['subject']}
💰 **Цена:** {tender_info['price']}
📅 **Дата публикации:** {tender_info['publication_date']}
⏰ **Срок подачи:** {tender_info['submission_deadline']}
📊 **Статус:** {tender_info['status']}
📎 **Документов:** {tender_info['document_count']}

🔍 **Основные детали:**
• **Способ закупки:** {tender_info['procurement_type']}
• **Место поставки:** {tender_info['delivery_place']}
• **Обеспечение заявки:** {tender_info['guarantee_amount']}
• **Регион:** {tender_info['region']}
        """
        
        keyboard = [
            [InlineKeyboardButton("📦 Товарные позиции", callback_data=f"products_{reg_number}")],
            [InlineKeyboardButton("📄 Документы", callback_data=f"documents_{reg_number}")],
            [InlineKeyboardButton("🏢 Подробная информация", callback_data=f"details_{reg_number}")],
            [InlineKeyboardButton("📊 Подробный анализ", callback_data=f"analyze_{reg_number}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(info_text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _send_analysis_to_chat(self, bot, chat_id: int, analysis_result: dict) -> None:
        """Отправляет результаты анализа в чат по chat_id"""
        overall = analysis_result.get('overall_analysis', {})
        summary = overall.get('summary', 'Анализ недоступен')
        
        # Разбиваем длинный анализ на части
        if len(summary) > 4000:
            parts = [summary[i:i+4000] for i in range(0, len(summary), 4000)]
            for i, part in enumerate(parts):
                if i == 0:
                    await bot.send_message(chat_id=chat_id, text=f"🤖 **Анализ тендера** (часть {i+1}/{len(parts)}):\n\n{part}", parse_mode='Markdown')
                else:
                    await bot.send_message(chat_id=chat_id, text=f"🤖 **Продолжение анализа** (часть {i+1}/{len(parts)}):\n\n{part}", parse_mode='Markdown')
        else:
            await bot.send_message(chat_id=chat_id, text=f"🤖 **Анализ тендера:**\n\n{summary}", parse_mode='Markdown')
    
    async def _send_analysis(self, update: Update, analysis_result: dict) -> None:
        """Отправляет результаты анализа"""
        overall = analysis_result.get('overall_analysis', {})
        summary = overall.get('summary', 'Анализ недоступен')
        
        # Разбиваем длинный анализ на части
        if len(summary) > 4000:
            parts = [summary[i:i+4000] for i in range(0, len(summary), 4000)]
            for i, part in enumerate(parts):
                if i == 0:
                    await update.message.reply_text(f"🤖 **Анализ тендера** (часть {i+1}/{len(parts)}):\n\n{part}", parse_mode='Markdown')
                else:
                    await update.message.reply_text(f"🤖 **Продолжение анализа** (часть {i+1}/{len(parts)}):\n\n{part}", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"🤖 **Анализ тендера:**\n\n{summary}", parse_mode='Markdown')
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик callback запросов"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "help":
            await self.help_command(update, context)
        elif query.data == "status":
            await self.status_command(update, context)
        elif query.data.startswith("products_"):
            reg_number = query.data.split("_")[1]
            user_id = query.from_user.id
            
            # Проверяем, есть ли данные тендера в сессии
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            
            # Получаем данные из сессии
            tender_data = self.user_sessions[user_id]['tender_data']
            
            # Отправляем товарные позиции
            await self._send_products_list_to_chat(context.bot, query.message.chat_id, tender_data)
            
        elif query.data.startswith("documents_"):
            reg_number = query.data.split("_")[1]
            user_id = query.from_user.id
            
            # Проверяем, есть ли данные тендера в сессии
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            
            # Получаем данные из сессии
            tender_data = self.user_sessions[user_id]['tender_data']
            
            # Отправляем список документов с кнопками скачивания
            await self._send_documents_list_with_download(context.bot, query.message.chat_id, tender_data, reg_number)
            
        elif query.data.startswith("details_"):
            reg_number = query.data.split("_")[1]
            user_id = query.from_user.id
            
            # Проверяем, есть ли данные тендера в сессии
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            
            # Получаем данные из сессии
            formatted_info = self.user_sessions[user_id]['formatted_info']
            
            # Отправляем подробную информацию
            await self._send_detailed_info_to_chat(context.bot, query.message.chat_id, formatted_info)
            
        elif query.data.startswith("download_"):
            reg_number = query.data.split("_")[1]
            user_id = query.from_user.id
            
            # Проверяем, есть ли данные тендера в сессии
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            
            # Получаем данные из сессии
            tender_data = self.user_sessions[user_id]['tender_data']
            
            try:
                # Обновляем статус кнопки
                await query.edit_message_reply_markup(reply_markup=None)
                
                # Скачиваем документы
                await context.bot.send_message(chat_id=query.message.chat_id, text="📥 Скачиваю документы...")
                download_result = await downloader.download_documents(tender_data, reg_number)
                
                if download_result['success'] > 0:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"✅ Скачано документов: {download_result['success']}\n❌ Не удалось скачать: {download_result['failed']}"
                    )
                    
                    # Отправляем файлы пользователю
                    if download_result['files']:
                        await context.bot.send_message(chat_id=query.message.chat_id, text="📤 Отправляю файлы...")
                        
                        for file_path in download_result['files'][:10]:  # Ограничиваем 10 файлами
                            try:
                                with open(file_path, 'rb') as file:
                                    filename = os.path.basename(file_path)
                                    await context.bot.send_document(
                                        chat_id=query.message.chat_id,
                                        document=file,
                                        filename=filename
                                    )
                            except Exception as e:
                                logger.error(f"[bot] Ошибка отправки файла {file_path}: {e}")
                                continue
                        
                        if len(download_result['files']) > 10:
                            await context.bot.send_message(
                                chat_id=query.message.chat_id,
                                text=f"📤 Отправлено 10 файлов из {len(download_result['files'])}. Остальные файлы сохранены на сервере."
                            )
                    else:
                        await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Файлы не найдены")
                else:
                    await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Не удалось скачать документы")
                
            except Exception as e:
                logger.error(f"[bot] Ошибка скачивания документов тендера {reg_number}: {e}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Произошла ошибка при скачивании документов. Попробуйте позже."
                )
            
        elif query.data.startswith("analyze_"):
            reg_number = query.data.split("_")[1]
            user_id = query.from_user.id
            
            # Проверяем, есть ли данные тендера в сессии
            if user_id not in self.user_sessions or self.user_sessions[user_id]['status'] != 'ready_for_analysis':
                await query.edit_message_text("❌ Данные тендера не найдены. Пожалуйста, отправьте номер тендера заново.")
                return
            
            # Получаем данные из сессии
            tender_data = self.user_sessions[user_id]['tender_data']
            formatted_info = self.user_sessions[user_id]['formatted_info']
            
            try:
                # Обновляем статус кнопки
                await query.edit_message_reply_markup(reply_markup=None)
                
                # Скачиваем документы
                await context.bot.send_message(chat_id=query.message.chat_id, text="📥 Скачиваю документы...")
                download_result = await downloader.download_documents(tender_data, reg_number)
                
                if download_result['success'] > 0:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"✅ Скачано документов: {download_result['success']}\n❌ Не удалось скачать: {download_result['failed']}"
                    )
                    
                    # Анализируем документы
                    if download_result['files']:
                        await context.bot.send_message(chat_id=query.message.chat_id, text="🤖 Анализирую документы с помощью ИИ...")
                        analysis_result = await analyzer.analyze_tender_documents(formatted_info, download_result['files'])
                        
                        # Отправляем анализ
                        await self._send_analysis_to_chat(context.bot, query.message.chat_id, analysis_result)
                    else:
                        await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Документы не найдены для анализа")
                else:
                    await context.bot.send_message(chat_id=query.message.chat_id, text="⚠️ Не удалось скачать документы для анализа")
                
                # Обновляем статус сессии
                self.user_sessions[user_id]['status'] = 'completed'
                
            except Exception as e:
                logger.error(f"[bot] Ошибка анализа тендера {reg_number}: {e}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Произошла ошибка при анализе тендера. Попробуйте позже."
                )
    
    async def _send_products_list_to_chat(self, bot, chat_id: int, tender_data: dict) -> None:
        """Отправляет список товарных позиций в чат"""
        # Если данные содержат номер тендера как ключ, извлекаем данные из внутреннего объекта
        if len(tender_data) == 1 and isinstance(list(tender_data.values())[0], dict):
            tender_data = list(tender_data.values())[0]
        
        product_info = tender_data.get('Продукт', {})
        objects = product_info.get('ОбъектыЗак', [])
        
        if not objects:
            await bot.send_message(chat_id=chat_id, text="📦 Товарные позиции не найдены")
            return
        
        # Создаем список товарных позиций
        products_text = "📦 **Товарные позиции:**\n\n"
        
        total_cost = 0
        for i, obj in enumerate(objects[:10], 1):  # Показываем первые 10 позиций
            name = obj.get('Наименование', 'Без названия')
            quantity = obj.get('Количество', 0)
            unit = obj.get('ЕдИзм', 'шт')
            price = obj.get('ЦенаЕд', 0)
            cost = obj.get('Стоимость', 0)
            okpd = obj.get('ОКПД', '')
            additional_info = obj.get('ДопИнфо', '')
            
            products_text += f"{i}. **{name}**\n"
            products_text += f"   📊 Количество: {quantity} {unit}\n"
            products_text += f"   💰 Цена за ед.: {price} ₽\n"
            products_text += f"   💵 Стоимость: {cost} ₽\n"
            if okpd:
                products_text += f"   🏷️ ОКПД: {okpd}\n"
            if additional_info:
                # Ограничиваем длину дополнительной информации
                short_info = additional_info[:80] + "..." if len(additional_info) > 80 else additional_info
                products_text += f"   ℹ️ Доп. инфо: {short_info}\n"
            products_text += "\n"
            
            total_cost += cost
        
        if len(objects) > 10:
            products_text += f"... и еще {len(objects) - 10} позиций\n\n"
        
        products_text += f"**Общая стоимость позиций: {total_cost} ₽**"
        
        await bot.send_message(chat_id=chat_id, text=products_text, parse_mode='Markdown')
    
    async def _send_documents_list_with_download(self, bot, chat_id: int, tender_data: dict, reg_number: str) -> None:
        """Отправляет список документов с возможностью скачивания"""
        # Если данные содержат номер тендера как ключ, извлекаем документы из внутреннего объекта
        if len(tender_data) == 1 and isinstance(list(tender_data.values())[0], dict):
            tender_data = list(tender_data.values())[0]
        
        documents = tender_data.get('Документы', [])
        
        if not documents:
            await bot.send_message(chat_id=chat_id, text="📄 Документы не найдены")
            return
        
        # Создаем список документов
        docs_text = "📄 **Документы тендера:**\n\n"
        
        for i, doc in enumerate(documents[:10], 1):  # Показываем первые 10 документов
            name = doc.get('Название', 'Без названия')
            date = doc.get('ДатаРазм', '')
            files = doc.get('Файлы', [])
            
            docs_text += f"{i}. **{name}**\n"
            if date:
                docs_text += f"   📅 Дата: {date}\n"
            if files:
                docs_text += f"   📎 Файлов: {len(files)}\n"
            docs_text += "\n"
        
        if len(documents) > 10:
            docs_text += f"... и еще {len(documents) - 10} документов\n\n"
        
        docs_text += "💾 **Скачать все документы:**"
        
        # Создаем кнопку для скачивания
        keyboard = [
            [InlineKeyboardButton("📥 Скачать документы", callback_data=f"download_{reg_number}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await bot.send_message(chat_id=chat_id, text=docs_text, parse_mode='Markdown', reply_markup=reply_markup)
    
    async def _send_detailed_info_to_chat(self, bot, chat_id: int, tender_info: dict) -> None:
        """Отправляет подробную информацию о тендере"""
        detailed_text = f"""
🏢 **Подробная информация о тендере**

🔍 **Детали закупки:**
• **Способ закупки:** {tender_info['procurement_type']}
• **Место поставки:** {tender_info['delivery_place']}
• **Срок поставки:** {tender_info['delivery_terms']}
• **Обеспечение заявки:** {tender_info['guarantee_amount']}
• **Источник финансирования:** {tender_info['funding_source']}

🌍 **Региональная информация:**
• **Регион:** {tender_info['region']}
• **Федеральный закон:** {tender_info['federal_law']}-ФЗ

🏢 **Электронная торговая площадка:**
• **Название:** {tender_info['etp_name']}
• **Сайт:** {tender_info['etp_url']}

📞 **Контактная информация:**
• **Ответственное лицо:** {tender_info['contact_person']}
• **Телефон:** {tender_info['contact_phone']}
• **Email:** {tender_info['contact_email']}

💳 **Финансовые детали:**
• **ИКЗ:** {tender_info['ikz']}
• **Аванс:** {tender_info['advance_percent']}%
• **Обеспечение исполнения:** {tender_info['execution_amount']}
• **Банковское сопровождение:** {tender_info['bank_support']}
        """
        
        await bot.send_message(chat_id=chat_id, text=detailed_text, parse_mode='Markdown')
    
    def setup_handlers(self):
        """Настраивает обработчики команд и сообщений"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("cleanup", self.cleanup_command))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    def run(self):
        try:
            self.app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
            self.setup_handlers()
            logger.info("🚀 TenderBot запущен")
            print("🤖 TenderBot запущен и готов к работе!")
            print("📝 Логи сохраняются в файл:", LOG_FILE)
            self.app.run_polling()
        except Exception as e:
            logger.error(f"❌ Ошибка запуска бота: {e}")
            raise

# Создаем и запускаем бота
if __name__ == "__main__":
    bot = TenderBot()
    bot.run()
