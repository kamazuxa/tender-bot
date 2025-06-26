import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
print("[analyzer] analyzer.py импортирован")
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
import fitz  # PyMuPDF
import docx2txt
import pandas as pd

logger = logging.getLogger(__name__)

class DocumentAnalyzer:
    def __init__(self, api_key: str, model: str = OPENAI_MODEL):
        self.api_key = api_key
        self.model = model
        self.client = OpenAI(api_key=api_key)
    
    async def analyze_tender_documents(self, tender_info: Dict, downloaded_files: List[Dict]) -> str:
        print("[analyzer] analyze_tender_documents (объединённый режим) вызван")
        logger.info("[analyzer] analyze_tender_documents (объединённый режим) вызван")
        if not downloaded_files:
            logger.info("[analyzer] 📄 Нет документов для анализа")
            return "Документы для анализа не найдены."
        # 1. Извлекаем тексты
        texts = []
        for file_info in downloaded_files:
            file_path = Path(file_info['path'])
            text = await self.extract_text_from_file(file_path)
            logger.info(f"[analyzer] {file_path} — длина текста: {len(text) if text else 0}")
            logger.info(f"[analyzer] {file_path} — первые 200 символов: {text[:200] if text else 'ПУСТО'}")
            if not text or len(text.strip()) < 100:
                logger.warning(f"[analyzer] Файл {file_path} проигнорирован (мало текста)")
                continue
            # Очистка мусора (футеры, даты, повторяющиеся заголовки)
            text = self.cleanup_text(text)
            texts.append((file_info.get('original_name', str(file_path)), text))
        if not texts:
            logger.info("[analyzer] Нет подходящих файлов для анализа")
            return "Нет подходящих файлов для анализа."
        # 2. Объединяем с метками
        doc_texts = [f"==== ДОКУМЕНТ: {name} ====" + "\n" + t for name, t in texts]
        full_text = "\n\n".join(doc_texts)
        logger.info(f"[analyzer] Итоговый full_text длина: {len(full_text)}")
        logger.info(f"[analyzer] Итоговый full_text первые 500 символов: {full_text[:500]}")
        # 3. Обрезаем если слишком длинно (лимит 15000 токенов ≈ 60000 символов)
        max_len = 60000
        if len(full_text) > max_len:
            logger.warning(f"[analyzer] Суммарный текст превышает лимит, будет усечён")
            # Равномерно сокращаем каждый документ
            n = len(doc_texts)
            chunk = max_len // n
            doc_texts = [t[:chunk] for t in doc_texts]
            full_text = "\n\n".join(doc_texts)
        # 4. Формируем промпт
        prompt = self.make_analysis_prompt(full_text)
        logger.info(f"DEBUG prompt preview: {prompt[:2000]}")
        logger.info(f"[analyzer] Отправляю в OpenAI объединённый промпт длиной {len(prompt)} символов")
        # 5. Один вызов к OpenAI
        analysis = await self._call_openai_api(prompt)
        if not analysis:
            logger.error("[analyzer] Не удалось получить анализ от OpenAI")
            return "❌ Не удалось получить анализ тендера. Попробуйте позже."
        return analysis
    
    async def extract_text_from_file(self, file_path: Path) -> Optional[str]:
        """Универсальное извлечение текста из файла (PDF, DOCX, XLSX, ZIP и др.)"""
        ext = file_path.suffix.lower()
        try:
            if ext == '.txt':
                import aiofiles
                async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return await f.read()
            elif ext == '.docx':
                return docx2txt.process(str(file_path))
            elif ext == '.doc':
                import subprocess
                result = subprocess.run(['antiword', str(file_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return result.stdout.decode('utf-8', errors='ignore')
            elif ext == '.pdf':
                text = ""
                with fitz.open(str(file_path)) as doc:
                    for page in doc:
                        text += page.get_text()
                return text
            elif ext in ['.xls', '.xlsx']:
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
                            text = await self.extract_text_from_file(tmp_path)
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
                            text = await self.extract_text_from_file(tmp_path)
                            if text:
                                texts.append(f'--- {member} ---\n{text}')
                            tmp_path.unlink(missing_ok=True)
                return '\n\n'.join(texts)
            else:
                return None
        except Exception as e:
            logger.error(f'[extract_text_from_file] ❌ Ошибка чтения {file_path}: {e}')
            return None
    
    def cleanup_text(self, text: str) -> str:
        """Удаляет мусор: футеры, даты, повторяющиеся заголовки и т.п."""
        import re
        # Удаляем повторяющиеся заголовки
        lines = text.splitlines()
        seen = set()
        cleaned = []
        for line in lines:
            l = line.strip()
            if l and l not in seen:
                cleaned.append(l)
                seen.add(l)
        text = "\n".join(cleaned)
        # Удаляем даты (простая эвристика)
        text = re.sub(r'\d{2,4}[./-]\d{2}[./-]\d{2,4}', '', text)
        # Удаляем футеры (по ключевым словам)
        text = re.sub(r'страница \d+ из \d+', '', text, flags=re.I)
        return text
    
    def make_analysis_prompt(self, full_text: str) -> str:
        """Генерирует промпт для объединённого анализа всех документов"""
        return f"""
Ты — эксперт по госзакупкам и анализу тендерной документации.

Вот полный текст всех документов закупки (ТЗ, контракт, приложения и др.), разделённых маркерами ==== ДОКУМЕНТ ====. Проанализируй их комплексно и выполни следующие задачи:

1. Дай краткое описание закупки: какие товары/услуги требуются, объёмы, особенности (ГОСТ, фасовка, сорт, единицы измерения, сроки и т.п.).
2. Определи потенциальные риски и подводные камни для участника закупки (неясности в ТЗ, требования к упаковке, ограничения по поставке, логистике, сертификации и т.д.).
3. Дай рекомендации: стоит ли участвовать в закупке с учётом этих рисков? Почему да или почему нет?
4. Сформируй поисковые запросы в Яндексе для каждой товарной позиции, чтобы найти поставщиков в России. Запросы должны быть максимально релевантными для нахождения коммерческих предложений, цен и контактов. Включай: – наименование товара (кратко), – сорт/марку/модель, – ГОСТ/ТУ, – фасовку/упаковку, – объём (если применимо), – ключевые слова: купить, оптом, цена, поставщик.

Формат ответа:
Анализ: <...>
Поисковые запросы:
1. <позиция>: <поисковый запрос>
2. ...
"""
    
    async def _call_openai_api(self, prompt: str) -> str:
        print("[analyzer] _call_openai_api вызван")
        logger.info("[analyzer] _call_openai_api вызван")
        try:
            logger.info(f"[analyzer] Отправляю в OpenAI prompt длиной {len(prompt)} символов")
            print(f"[analyzer] Отправляю в OpenAI prompt длиной {len(prompt)} символов")
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
            print(f"[analyzer] Ответ OpenAI (первые 500 символов): {answer[:500]}")
            return answer
        except Exception as e:
            logger.error(f"[analyzer] ❌ Ошибка при обращении к OpenAI: {e}")
            print(f"[analyzer] ❌ Ошибка при обращении к OpenAI: {e}")
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