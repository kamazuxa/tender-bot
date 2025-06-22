import httpx
import logging
import json
from typing import Dict, Optional, List
from config import DAMIA_API_KEY

logger = logging.getLogger(__name__)

class DamiaAPIError(Exception):
    """Исключение для ошибок API DaMIA"""
    pass

class DamiaClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.damia.ru"
        self.headers = {"Authorization": f"Api-Key {api_key}"}
    
    async def get_zakupka(self, reg_number: str, actual: int = 1) -> Optional[Dict]:
        url = f"https://api.damia.ru/zakupki/zakupka"
        params = {"regn": reg_number, "actual": actual, "key": self.api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200 and resp.text.strip():
                return resp.json()
        return None
    
    async def get_contract(self, reg_number: str) -> Optional[Dict]:
        url = f"https://api.damia.ru/zakupki/contract"
        params = {"regn": reg_number, "key": self.api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200 and resp.text.strip():
                return resp.json()
        return None
    
    async def zsearch(self, q: str, **kwargs) -> Optional[Dict]:
        url = f"https://damia.ru/api-zakupki/zsearch"
        params = {"q": q, "key": self.api_key}
        params.update(kwargs)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200 and resp.text.strip():
                return resp.json()
        return None
    
    async def get_tender_info(self, reg_number: str) -> Optional[Dict]:
        """
        Получает информацию о тендере по регистрационному номеру
        Пробует разные эндпоинты для поиска данных
        """
        # Сначала пробуем zakupka, потом contract
        data = await self.get_zakupka(reg_number)
        if data:
            return data
        data = await self.get_contract(reg_number)
        if data:
            return data
        return None
    
    def _is_empty_response(self, data: Dict) -> bool:
        """Проверяет, является ли ответ пустым или неинформативным"""
        if not data:
            return True
        
        # Проверяем основные поля, которые должны быть в ответе
        required_fields = ['РазмОрг', 'Продукт', 'НачЦена']
        return not any(field in data for field in required_fields)
    
    def extract_tender_number(self, text: str) -> Optional[str]:
        """
        Извлекает номер тендера из текста (ссылка или номер)
        Поддерживает различные форматы
        """
        import re
        
        # Паттерны для поиска номеров тендеров
        patterns = [
            r'\d{19}',  # 19-значный номер
            r'\d{20}',  # 20-значный номер
            r'zakupki\.gov\.ru/epz/order/notice/.*?(\d{19})',  # Ссылка на госзакупки
            r'zakupki\.gov\.ru/.*?(\d{19})',  # Общая ссылка на госзакупки
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1) if len(match.groups()) > 0 else match.group(0)
        
        return None
    
    def format_tender_info(self, data: Dict) -> Dict:
        """
        Форматирует данные тендера в удобный для отображения вид
        """
        try:
            # Извлекаем основную информацию
            customer = data.get('РазмОрг', {}).get('НаимПолн', 'Не указан')
            subject = data.get('Продукт', {}).get('Название', 'Не указан')
            
            # Обрабатываем цену
            price_info = data.get('НачЦена', {})
            price = price_info.get('Сумма', 'Не указана')
            currency = price_info.get('Валюта', '₽')
            
            # Обрабатываем даты
            publication_date = data.get('ДатаПубл', 'Не указана')
            submission_deadline = data.get('ДатаОкончПодач', 'Не указана')
            
            # Обрабатываем статус
            status = data.get('Статус', 'Не указан')
            
            # Обрабатываем документы
            documents = data.get('Документы', [])
            doc_count = len(documents) if documents else 0
            
            return {
                'customer': customer,
                'subject': subject,
                'price': f"{price} {currency}" if price != 'Не указана' else price,
                'publication_date': publication_date,
                'submission_deadline': submission_deadline,
                'status': status,
                'document_count': doc_count,
                'raw_data': data  # Сохраняем исходные данные для дальнейшей обработки
            }
            
        except Exception as e:
            logger.error(f"[damia] ❌ Ошибка форматирования данных: {e}")
            return {
                'customer': 'Ошибка обработки',
                'subject': 'Ошибка обработки',
                'price': 'Ошибка обработки',
                'publication_date': 'Ошибка обработки',
                'submission_deadline': 'Ошибка обработки',
                'status': 'Ошибка обработки',
                'document_count': 0,
                'raw_data': data
            }

# Создаем глобальный экземпляр клиента
damia_client = DamiaClient(DAMIA_API_KEY)

async def get_info_by_regnumber(reg_number: str) -> Optional[Dict]:
    """Совместимость с существующим кодом"""
    return await damia_client.get_tender_info(reg_number)

def extract_tender_number(text: str) -> Optional[str]:
    """Совместимость с существующим кодом"""
    return damia_client.extract_tender_number(text)
