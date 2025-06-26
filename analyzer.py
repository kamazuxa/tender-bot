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
import hashlib

logger = logging.getLogger(__name__)

class DocumentAnalyzer:
    def __init__(self, api_key: str, model: str = OPENAI_MODEL):
        self.api_key = api_key
        self.model = model
        self.client = OpenAI(api_key=api_key)
    
    async def analyze_tender_documents(self, tender_info: Dict, downloaded_files: List[Dict]) -> str:
        print("[analyzer] analyze_tender_documents (эконом режим) вызван")
        logger.info("[analyzer] analyze_tender_documents (эконом режим) вызван")
        if not downloaded_files:
            logger.info("[analyzer] 📄 Нет документов для анализа")
            return "Документы для анализа не найдены."
        # 1. Извлекаем тексты и собираем full_text
        full_chunks = []
        for file_info in downloaded_files:
            file_path = Path(file_info['path'])
            try:
                text = await self.extract_text_from_file(file_path)
                if not text or len(text.strip()) < 50:
                    logger.warning(f"[analyzer] Пустой или слишком короткий текст: {file_path}")
                    continue
                header = f"==== ДОКУМЕНТ: {file_info.get('original_name', str(file_path))} ====\n{text.strip()}\n"
                full_chunks.append(header)
                logger.info(f"[analyzer] {file_path} — длина текста: {len(text)}")
                logger.info(f"[analyzer] {file_path} — первые 200 символов: {text.strip()[:200]}")
            except Exception as e:
                logger.error(f"[analyzer] Ошибка при обработке {file_path}: {e}")
        full_text = "\n\n".join(full_chunks)
        logger.info(f"[analyzer] Итоговый full_text длина: {len(full_text)}")
        logger.info(f"[analyzer] Итоговый full_text первые 500 символов: {full_text[:500]}")
        # 2. Обрезаем если слишком длинно (лимит 120000 символов)
        if len(full_text) > 120000:
            logger.warning("[analyzer] Суммарный текст превышает лимит, будет усечён")
            full_text = full_text[:120000]
        # 3. Кеширование по хешу full_text
        cache_key = hashlib.sha256(full_text.encode('utf-8')).hexdigest()
        cache_file = Path(f"analysis_cache/{cache_key}.txt")
        if cache_file.exists():
            logger.info(f"[analyzer] Найден кеш анализа по хешу: {cache_key}")
            return cache_file.read_text(encoding='utf-8')
        # 4. Формируем messages
        prompt_instructions = (
            "Проанализируй их комплексно и выполни следующие задачи:\n\n"
            "1. Дай краткое описание закупки: какие товары/услуги требуются, объёмы, особенности (ГОСТ, фасовка, сорт, единицы измерения, сроки и т.п.).\n"
            "2. Определи потенциальные риски и подводные камни для участника закупки (неясности в ТЗ, требования к упаковке, ограничения по поставке, логистике, сертификации и т.д.).\n"
            "3. Дай рекомендации: стоит ли участвовать в закупке с учётом этих рисков? Почему да или почему нет?\n"
            "4. Сформируй поисковые запросы в Яндексе для каждой товарной позиции, чтобы найти поставщиков в России. Запросы должны быть максимально релевантными для нахождения коммерческих предложений, цен и контактов. Включай: – наименование товара (кратко), – сорт/марку/модель, – ГОСТ/ТУ, – фасовку/упаковку, – объём (если применимо), – ключевые слова: купить, оптом, цена, поставщик.\n\n"
            "Формат ответа:\n"
            "Анализ: <...>\n"
            "Поисковые запросы:\n"
            "1. <позиция>: <поисковый запрос>\n"
            "2. ..."
        )
        messages = [
            {"role": "system", "content": "Ты — эксперт по госзакупкам и анализу тендерной документации."},
            {"role": "user", "content": full_text},
            {"role": "user", "content": prompt_instructions}
        ]
        logger.info(f"[analyzer] messages[1] length: {len(full_text)}")
        logger.info(f"[analyzer] prompt preview (messages[2]): {prompt_instructions[:500]}")
        # 5. Отправляем в OpenAI
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=2048
                )
            )
            answer = response.choices[0].message.content.strip()
            logger.info(f"[analyzer] Ответ OpenAI (первые 500 символов): {answer[:500]}")
            # 6. Сохраняем в кеш
            cache_file.parent.mkdir(exist_ok=True)
            cache_file.write_text(answer, encoding='utf-8')
            return answer
        except Exception as e:
            logger.error(f"[analyzer] Ошибка запроса к OpenAI: {e}")
            return f"❌ Ошибка запроса к OpenAI: {e}"
    
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
    
    async def _call_openai_api(self, blocks: list) -> str:
        print("[analyzer] _call_openai_api (messages) вызван")
        logger.info("[analyzer] _call_openai_api (messages) вызван")
        try:
            # 1. Инструкция
            system_prompt = (
                "Ты — эксперт по госзакупкам и анализу тендерной документации. "
                "Тебе будут поочерёдно отправлены блоки текста из разных документов закупки. "
                "Не отвечай до финального сообщения! Просто запоминай и анализируй текст."
            )
            messages = [
                {"role": "system", "content": system_prompt}
            ]
            # 2. Добавляем каждый блок как отдельное user-сообщение
            for idx, block in enumerate(blocks):
                messages.append({
                    "role": "user",
                    "content": f"==== ДОКУМЕНТ {idx+1} ====\n{block}"
                })
            logger.info(f"[analyzer] Всего user-блоков для OpenAI: {len(blocks)}")
            for i, m in enumerate(messages):
                logger.info(f"[analyzer] messages[{i}] role={m['role']} len={len(m['content'])}")
            # 3. Финальный промпт
            final_prompt = (
                "Проанализируй все документы, которые были отправлены выше, и выполни следующие задачи по пунктам:\n"
                "1. Дай краткое описание закупки: какие товары/услуги требуются, объёмы, особенности (ГОСТ, фасовка, сорт, единицы измерения, сроки и т.п.).\n"
                "2. Определи потенциальные риски и подводные камни для участника закупки (неясности в ТЗ, требования к упаковке, ограничения по поставке, логистике, сертификации и т.д.).\n"
                "3. Дай рекомендации: стоит ли участвовать в закупке с учётом этих рисков? Почему да или почему нет?\n"
                "4. Сформируй поисковые запросы в Яндексе для каждой товарной позиции, чтобы найти поставщиков в России. Запросы должны быть максимально релевантными для нахождения коммерческих предложений, цен и контактов. Включай: – наименование товара (кратко), – сорт/марку/модель, – ГОСТ/ТУ, – фасовку/упаковку, – объём (если применимо), – ключевые слова: купить, оптом, цена, поставщик.\n\n"
                "Формат ответа:\nАнализ: <...>\nПоисковые запросы:\n1. <позиция>: <поисковый запрос>\n2. ..."
            )
            messages.append({"role": "user", "content": final_prompt})
            logger.info(f"[analyzer] Финальный messages[{len(messages)-1}] len={len(final_prompt)}")
            # 4. Отправляем в OpenAI
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
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