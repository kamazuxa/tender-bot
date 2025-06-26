import logging
import asyncio
from typing import Dict, List, Optional
from pathlib import Path
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, USE_VPN_FOR_OPENAI, VPN_INTERFACE
import mimetypes
try:
    import pytesseract
    from PIL import Image
    OCR_SUPPORT = True
except ImportError:
    OCR_SUPPORT = False
try:
    import PyPDF2
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

logger = logging.getLogger(__name__)

class DocumentAnalyzer:
    def __init__(self, api_key: str, model: str = OPENAI_MODEL):
        self.api_key = api_key
        self.model = model
        self.client = OpenAI(api_key=api_key)
    
    async def analyze_tender_documents(self, tender_info: Dict, downloaded_files: List[Dict]) -> Dict:
        """
        Анализирует документы тендера с помощью OpenAI
        """
        if not downloaded_files:
            logger.info("[analyzer] 📄 Нет документов для анализа")
            return self._create_empty_analysis()
        
        logger.info(f"[analyzer] 🤖 Начинаем анализ {len(downloaded_files)} документов")
        
        try:
            # Подготавливаем контекст о тендере
            tender_context = self._prepare_tender_context(tender_info)
            
            # Анализируем каждый документ
            document_analyses = []
            for file_info in downloaded_files:
                try:
                    analysis = await self._analyze_single_document(file_info, tender_context)
                    if analysis:
                        document_analyses.append(analysis)
                except Exception as e:
                    logger.error(f"[analyzer] ❌ Ошибка анализа документа {file_info.get('name', 'unknown')}: {e}")
            
            # Создаем общий анализ
            overall_analysis = await self._create_overall_analysis(tender_info, document_analyses)
            logger.info(f"[analyzer] ✅ Общий анализ: {overall_analysis}")
            
            return {
                "tender_summary": tender_context,
                "document_analyses": document_analyses,
                "overall_analysis": overall_analysis,
                "analysis_timestamp": asyncio.get_event_loop().time()
            }
        except Exception as e:
            logger.error(f"[analyzer] ❌ Ошибка в analyze_tender_documents: {e}")
            return None
    
    def _prepare_tender_context(self, tender_info: Dict) -> Dict:
        """Подготавливает контекстную информацию о тендере"""
        try:
            raw_data = tender_info.get('raw_data', {})
            
            return {
                "customer": tender_info.get('customer', 'Не указан'),
                "subject": tender_info.get('subject', 'Не указан'),
                "price": tender_info.get('price', 'Не указана'),
                "publication_date": tender_info.get('publication_date', 'Не указана'),
                "submission_deadline": tender_info.get('submission_deadline', 'Не указана'),
                "status": tender_info.get('status', 'Не указан'),
                "document_count": tender_info.get('document_count', 0),
                "raw_data_summary": self._extract_key_info(raw_data)
            }
        except Exception as e:
            logger.error(f"[analyzer] ❌ Ошибка подготовки контекста: {e}")
            return {"error": "Ошибка обработки данных тендера"}
    
    def _extract_key_info(self, raw_data: Dict) -> Dict:
        """Извлекает ключевую информацию из сырых данных"""
        try:
            return {
                "procurement_type": raw_data.get('ТипЗакупки', 'Не указан'),
                "procurement_method": raw_data.get('СпособЗакупки', 'Не указан'),
                "delivery_place": raw_data.get('МестоПоставки', 'Не указано'),
                "delivery_terms": raw_data.get('СрокПоставки', 'Не указан'),
                "requirements": raw_data.get('Требования', {}),
                "conditions": raw_data.get('Условия', {})
            }
        except Exception as e:
            logger.error(f"[analyzer] ❌ Ошибка извлечения ключевой информации: {e}")
            return {}
    
    async def _analyze_single_document(self, file_info: Dict, tender_context: Dict) -> Optional[Dict]:
        """Анализирует один документ"""
        try:
            file_path = Path(file_info['path'])
            if not file_path.exists():
                logger.warning(f"[analyzer] ⚠️ Файл не найден: {file_path}")
                return None
            
            # Читаем содержимое файла
            content = await self._read_file_content(file_path)
            if not content:
                logger.warning(f"[analyzer] ⚠️ Пустое содержимое файла: {file_path}")
                return None
            
            # Создаем промпт для анализа
            prompt = self._create_analysis_prompt(content, tender_context, file_info['original_name'])
            logger.info(f"[analyzer] Промпт для GPT (первые 500 символов): {prompt[:500]}")
            
            # Отправляем запрос к OpenAI
            analysis = await self._call_openai_api(prompt)
            logger.info(f"[analyzer] Ответ GPT (первые 500 символов): {str(analysis)[:500]}")
            
            return {
                "file_name": file_info['original_name'],
                "file_size": file_info['size'],
                "analysis": analysis,
                "content_preview": content[:500] + "..." if len(content) > 500 else content
            }
            
        except Exception as e:
            logger.error(f"[analyzer] ❌ Ошибка анализа документа: {e}")
            return None
    
    async def _read_file_content(self, file_path: Path) -> Optional[str]:
        """Читает содержимое файла, поддерживает текст, docx, doc, pdf, xls, xlsx, изображения, архивы"""
        import subprocess
        ext = file_path.suffix.lower()
        try:
            if ext == '.txt':
                import aiofiles
                async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return await f.read()
            elif ext == '.docx':
                import docx2txt
                return docx2txt.process(str(file_path))
            elif ext == '.doc':
                # Требуется установленный antiword
                result = subprocess.run(['antiword', str(file_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return result.stdout.decode('utf-8', errors='ignore')
            elif ext == '.pdf':
                text = ""
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page in pdf_reader.pages:
                        text += page.extract_text() + "\n"
                return text
            elif ext in ['.xls', '.xlsx']:
                import pandas as pd
                df = pd.read_excel(str(file_path), dtype=str, engine='openpyxl' if ext == '.xlsx' else None)
                return df.to_string(index=False)
            elif ext in ['.jpg', '.jpeg', '.png']:
                from PIL import Image
                import pytesseract
                img = Image.open(file_path)
                return pytesseract.image_to_string(img, lang='rus+eng')
            elif ext == '.zip':
                import zipfile, tempfile
                texts = []
                with zipfile.ZipFile(file_path, 'r') as zf:
                    for member in zf.namelist():
                        if not member.endswith('/'):
                            with zf.open(member) as f, tempfile.NamedTemporaryFile(delete=False, suffix=Path(member).suffix) as tmp:
                                tmp.write(f.read())
                                tmp_path = Path(tmp.name)
                            text = await self._read_file_content(tmp_path)
                            if text:
                                texts.append(f'--- {member} ---\n{text}')
                            tmp_path.unlink(missing_ok=True)
                return '\n\n'.join(texts)
            elif ext == '.rar':
                import rarfile, tempfile
                texts = []
                with rarfile.RarFile(str(file_path)) as rf:
                    for member in rf.namelist():
                        if not member.endswith('/'):
                            with rf.open(member) as f, tempfile.NamedTemporaryFile(delete=False, suffix=Path(member).suffix) as tmp:
                                tmp.write(f.read())
                                tmp_path = Path(tmp.name)
                            text = await self._read_file_content(tmp_path)
                            if text:
                                texts.append(f'--- {member} ---\n{text}')
                            tmp_path.unlink(missing_ok=True)
                return '\n\n'.join(texts)
            else:
                return None
        except Exception as e:
            logger.error(f'[analyzer] ❌ Ошибка чтения {file_path}: {e}')
            return None
    
    def _create_analysis_prompt(self, content: str, tender_context: Dict, filename: str) -> str:
        """Создает промпт для анализа документа"""
        return f"""
Проанализируй документ тендера "{filename}" и предоставь структурированный анализ.

Контекст тендера:
- Заказчик: {tender_context.get('customer', 'Не указан')}
- Предмет: {tender_context.get('subject', 'Не указан')}
- Цена: {tender_context.get('price', 'Не указана')}
- Срок подачи: {tender_context.get('submission_deadline', 'Не указан')}

Содержимое документа:
{content[:4000]}  # Ограничиваем размер для API

Пожалуйста, проанализируй документ и предоставь:

1. **Краткое резюме** (2-3 предложения)
2. **Товарные позиции** (список товаров/услуг)
3. **Требования к упаковке** (если указаны)
4. **Требования к сорту/качеству** (если указаны)
5. **Ключевые требования** (важные условия участия)
6. **Рекомендации** (стоит ли участвовать, на что обратить внимание)

Формат ответа должен быть структурированным и удобным для чтения.
"""
    
    async def _call_openai_api(self, prompt: str) -> str:
        try:
            logger.info(f"[analyzer] Отправляю в OpenAI prompt длиной {len(prompt)} символов")
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1200,
                    temperature=0.2,
                )
            )
            answer = response.choices[0].message.content
            logger.info(f"[analyzer] Ответ OpenAI (первые 500 символов): {answer[:500]}")
            return answer
        except Exception as e:
            logger.error(f"[analyzer] ❌ Ошибка при обращении к OpenAI: {e}")
            return None
    
    async def _setup_vpn_connection(self):
        """Настраивает VPN соединение для запросов к OpenAI"""
        try:
            # Здесь можно добавить логику настройки VPN
            # Например, проверка статуса WireGuard интерфейса
            logger.info(f"[analyzer] 🔒 Используется VPN интерфейс: {VPN_INTERFACE}")
        except Exception as e:
            logger.warning(f"[analyzer] ⚠️ Ошибка настройки VPN: {e}")
    
    async def _create_overall_analysis(self, tender_info: Dict, document_analyses: List[Dict]) -> Dict:
        """Создает общий анализ на основе всех документов"""
        if not document_analyses:
            return {"summary": "Нет документов для анализа"}
        
        try:
            # Объединяем анализы всех документов
            combined_analysis = "\n\n".join([
                f"Документ: {doc['file_name']}\n{doc['analysis']}"
                for doc in document_analyses
            ])
            
            prompt = f"""
На основе анализа всех документов тендера, создай общее резюме:

Информация о тендере:
- Заказчик: {tender_info.get('customer', 'Не указан')}
- Предмет: {tender_info.get('subject', 'Не указан')}
- Цена: {tender_info.get('price', 'Не указана')}

Анализ документов:
{combined_analysis[:3000]}

Предоставь:
1. **Общее резюме тендера** (3-4 предложения)
2. **Основные товарные позиции**
3. **Ключевые требования и условия**
4. **Риски и особенности**
5. **Рекомендация по участию** (участвовать/не участвовать и почему)
6. **Оценка сложности** (простой/средний/сложный)

Будь конкретным и практичным в рекомендациях.
"""
            
            overall_analysis = await self._call_openai_api(prompt)
            
            return {
                "summary": overall_analysis,
                "document_count": len(document_analyses),
                "analysis_quality": "complete" if document_analyses else "incomplete"
            }
            
        except Exception as e:
            logger.error(f"[analyzer] ❌ Ошибка создания общего анализа: {e}")
            return {"summary": f"Ошибка создания общего анализа: {str(e)}"}
    
    def _create_empty_analysis(self) -> Dict:
        """Создает пустой анализ при отсутствии документов"""
        return {
            "tender_summary": {},
            "document_analyses": [],
            "overall_analysis": {
                "summary": "Документы для анализа не найдены",
                "document_count": 0,
                "analysis_quality": "no_documents"
            },
            "analysis_timestamp": asyncio.get_event_loop().time()
        }

# Создаем глобальный экземпляр анализатора
analyzer = DocumentAnalyzer(OPENAI_API_KEY)

async def analyze_tender_documents(tender_info: Dict, downloaded_files: List[Dict]) -> Dict:
    """Совместимость с существующим кодом"""
    return await analyzer.analyze_tender_documents(tender_info, downloaded_files) 