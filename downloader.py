import os
import aiofiles
import aiohttp
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from config import DOWNLOAD_DIR, MAX_FILE_SIZE, SUPPORTED_EXTENSIONS
import zipfile
try:
    import rarfile
    RAR_SUPPORT = True
except ImportError:
    RAR_SUPPORT = False

logger = logging.getLogger(__name__)

class DocumentDownloader:
    def __init__(self, download_dir: str = DOWNLOAD_DIR):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
    
    async def download_documents(self, tender_data: Dict, reg_number: str) -> Dict:
        """
        Асинхронно скачивает документы тендера
        """
        # Если tender_data — это словарь с одним ключом (номером тендера), работаем с его содержимым
        if len(tender_data) == 1 and isinstance(list(tender_data.values())[0], dict):
            tender_data = list(tender_data.values())[0]

        documents = tender_data.get("Документы", [])
        all_files = []
        for doc in documents:
            files = doc.get("Файлы", [])
            for f in files:
                all_files.append(f)

        if not all_files:
            logger.info(f"[downloader] 📄 Документы не найдены для тендера {reg_number}")
            return {"success": 0, "failed": 0, "files": []}

        logger.info(f"[downloader] 📥 Начинаем скачивание {len(all_files)} документов")

        downloaded_files = []
        success_count = 0
        failed_count = 0
        # Заменяем documents на all_files в цикле скачивания
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            for file_info in all_files:
                try:
                    result = await self._download_single_document(session, file_info, reg_number)
                    if result:
                        downloaded_files.append(result)
                        # Если это архив, распаковываем
                        ext = Path(result['saved_name']).suffix.lower()
                        if ext == '.zip':
                            extracted = self._extract_zip(result['path'])
                            downloaded_files.extend(extracted)
                        elif ext == '.rar' and RAR_SUPPORT:
                            extracted = self._extract_rar(result['path'])
                            downloaded_files.extend(extracted)
                        success_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    logger.error(f"[downloader] ❌ Ошибка скачивания файла: {e}")
                    failed_count += 1
        
        logger.info(f"[downloader] ✅ Скачивание завершено: {success_count} успешно, {failed_count} не удалось")
        
        return {
            "success": success_count,
            "failed": failed_count,
            "files": downloaded_files
        }
    
    async def _download_single_document(self, session: aiohttp.ClientSession, doc: Dict, reg_number: str) -> Optional[Dict]:
        """
        Скачивает один документ по Url и Названию, определяя расширение по Content-Type
        """
        import mimetypes
        import os

        url = doc.get("Url")
        name = doc.get("Название", "unnamed")

        if not url:
            logger.warning(f"[downloader] ⚠️ Нет ссылки (Url) для файла {name}")
            return None

        # Подделка заголовков браузера
        referer = f"https://zakupki.gov.ru/epz/order/notice/ea20/view/common-info.html?regNumber={reg_number}"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "ru,en;q=0.9",
            "Referer": referer
        }

        try:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.warning(f"[downloader] ⚠️ HTTP {response.status} для {name}")
                    return None

                # 1. Пытаемся получить имя файла из Content-Disposition
                import re
                cd = response.headers.get("Content-Disposition")
                filename = None
                if cd:
                    match = re.search(r'filename="?([^";]+)"?', cd)
                    if match:
                        filename = match.group(1)

                # 2. Если не нашли — используем название из API
                if not filename:
                    filename = name

                # 3. Определяем расширение
                ext = os.path.splitext(filename)[1]
                if not ext:
                    # Если не удалось — ставим .pdf по умолчанию
                    ext = ".pdf"
                    filename += ext

                # 4. Создаём безопасное имя файла
                safe_filename = self._create_safe_filename(reg_number, filename)
                file_path = self.download_dir / safe_filename

                # Проверяем размер файла
                content_length = response.headers.get('content-length')
                if content_length and int(content_length) > MAX_FILE_SIZE:
                    logger.warning(f"[downloader] ⚠️ Файл слишком большой: {name} ({content_length} байт)")
                    return None

                # Скачиваем файл
                content = await response.read()
                if len(content) > MAX_FILE_SIZE:
                    logger.warning(f"[downloader] ⚠️ Файл превышает лимит после скачивания: {name}")
                    return None

                async with aiofiles.open(file_path, 'wb') as f:
                    await f.write(content)

                logger.info(f"[downloader] ✅ Скачан файл: {safe_filename}")

                return {
                    "original_name": name,
                    "saved_name": safe_filename,
                    "path": str(file_path),
                    "size": len(content),
                    "url": url
                }
        except aiohttp.ClientError as e:
            logger.error(f"[downloader] 🌐 Ошибка сети при скачивании {name}: {e}")
        except Exception as e:
            logger.error(f"[downloader] ❌ Ошибка при скачивании {name}: {e}")
        return None
    
    def _is_supported_extension(self, filename: str) -> bool:
        """Проверяет, поддерживается ли расширение файла"""
        return any(filename.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)
    
    def _create_safe_filename(self, reg_number: str, original_name: str) -> str:
        """Создает безопасное имя файла"""
        import re
        from datetime import datetime
        
        # Убираем небезопасные символы
        safe_name = re.sub(r'[^\w\-_.]', '_', original_name)
        
        # Добавляем временную метку для уникальности
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        return f"{reg_number}_{timestamp}_{safe_name}"
    
    def _extract_zip(self, file_path: str) -> List[Dict]:
        """Распаковывает zip-архив и возвращает список файлов"""
        extracted = []
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                for member in zf.namelist():
                    ext = Path(member).suffix.lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        out_path = self.download_dir / Path(member).name
                        zf.extract(member, self.download_dir)
                        extracted.append({
                            "original_name": member,
                            "saved_name": Path(member).name,
                            "path": str(out_path),
                            "size": out_path.stat().st_size,
                            "uid": None
                        })
        except Exception as e:
            logger.error(f"[downloader] ❌ Ошибка распаковки zip: {e}")
        return extracted
    
    def _extract_rar(self, file_path: str) -> List[Dict]:
        """Распаковывает rar-архив и возвращает список файлов"""
        extracted = []
        if not RAR_SUPPORT:
            logger.warning("[downloader] RAR архивы не поддерживаются (rarfile не установлен)")
            return extracted
        try:
            with rarfile.RarFile(file_path) as rf:
                for member in rf.namelist():
                    ext = Path(member).suffix.lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        out_path = self.download_dir / Path(member).name
                        rf.extract(member, self.download_dir)
                        extracted.append({
                            "original_name": member,
                            "saved_name": Path(member).name,
                            "path": str(out_path),
                            "size": out_path.stat().st_size,
                            "uid": None
                        })
        except Exception as e:
            logger.error(f"[downloader] ❌ Ошибка распаковки rar: {e}")
        return extracted
    
    def get_downloaded_files(self, reg_number: str) -> List[Dict]:
        """Получает список скачанных файлов для тендера"""
        files = []
        for file_path in self.download_dir.glob(f"{reg_number}_*"):
            if file_path.is_file():
                files.append({
                    "name": file_path.name,
                    "path": str(file_path),
                    "size": file_path.stat().st_size
                })
        return files
    
    def cleanup_old_files(self, max_age_hours: int = 24) -> int:
        """Удаляет старые файлы для экономии места"""
        import time
        from datetime import datetime, timedelta
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        deleted_count = 0
        
        for file_path in self.download_dir.iterdir():
            if file_path.is_file():
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_time:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                        logger.info(f"[downloader] 🗑️ Удален старый файл: {file_path.name}")
                    except Exception as e:
                        logger.error(f"[downloader] ❌ Ошибка удаления файла {file_path.name}: {e}")
        
        return deleted_count

# Создаем глобальный экземпляр загрузчика
downloader = DocumentDownloader()

# Функции для совместимости с существующим кодом
async def download_documents(tender_data: Dict, reg_number: str) -> Dict:
    """Совместимость с существующим кодом"""
    return await downloader.download_documents(tender_data, reg_number)

def download_documents_sync(tender_data: Dict, reg_number: str) -> Dict:
    """Синхронная версия для совместимости"""
    import asyncio
    return asyncio.run(downloader.download_documents(tender_data, reg_number))
