import httpx
import logging
import json
import asyncio
from typing import Dict, Optional, List
from config import DAMIA_API_KEY

logger = logging.getLogger(__name__)

class DamiaAPIError(Exception):
    """Исключение для ошибок API DaMIA"""
    pass

# Retry настройки
MAX_RETRIES = 3
RETRY_DELAY = 1  # секунды

def retry_on_error(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """Декоратор для retry-логики"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"[damia] Попытка {attempt + 1}/{max_retries} не удалась: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay * (2 ** attempt))  # Экспоненциальная задержка
            logger.error(f"[damia] Все попытки исчерпаны: {last_exception}")
            raise last_exception
        return wrapper
    return decorator

class DamiaClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.damia.ru"
        self.headers = {"Authorization": f"Api-Key {api_key}"}
    
    @retry_on_error()
    async def get_zakupka(self, reg_number: str, actual: int = 1) -> Optional[Dict]:
        url = f"https://api.damia.ru/zakupki/zakupka"
        params = {"regn": reg_number, "actual": actual, "key": self.api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200 and resp.text.strip():
                return resp.json()
        return None
    
    @retry_on_error()
    async def get_contract(self, reg_number: str) -> Optional[Dict]:
        url = f"https://api.damia.ru/zakupki/contract"
        params = {"regn": reg_number, "key": self.api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200 and resp.text.strip():
                return resp.json()
        return None
    
    @retry_on_error()
    async def zsearch(self, q: str, **kwargs) -> Optional[Dict]:
        url = f"https://damia.ru/api-zakupki/zsearch"
        params = {"q": q, "key": self.api_key}
        params.update(kwargs)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200 and resp.text.strip():
                return resp.json()
        return None
    
    @retry_on_error()
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
            r'zakupki\.gov\.ru/epz/order/notice/.*?(\d{19})',  # Ссылка на госзакупки с 19-значным номером
            r'zakupki\.gov\.ru/.*?(\d{19})',  # Общая ссылка на госзакупки с 19-значным номером
            r'noticeInfoId=(\d+)',  # Новый формат с noticeInfoId
            r'regNumber=(\d+)',  # Формат с regNumber
            r'orderId=(\d+)',  # Формат с orderId
            r'zakupki\.gov\.ru/epz/order/notice/notice223/common-info\.html\?noticeInfoId=(\d+)',  # Конкретный формат 223-ФЗ
            r'zakupki\.gov\.ru/epz/order/notice/ea44/common-info\.html\?regNumber=(\d+)',  # Формат 44-ФЗ
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
            # Если ответ содержит только один ключ — номер тендера, работаем с его содержимым
            if len(data) == 1 and isinstance(list(data.values())[0], dict):
                data = list(data.values())[0]

            # Заказчик
            customer = 'Не указан'
            customer_inn = 'Не указан'
            customer_address = 'Не указан'
            
            # Пробуем получить данные заказчика из разных полей
            if 'РазмОрг' in data and isinstance(data['РазмОрг'], dict):
                customer = data['РазмОрг'].get('НаимПолн', 'Не указан')
                customer_inn = data['РазмОрг'].get('ИНН', 'Не указан')
                customer_address = data['РазмОрг'].get('АдресПолн', 'Не указан')
            elif 'Заказчик' in data and isinstance(data['Заказчик'], list) and data['Заказчик']:
                customer = data['Заказчик'][0].get('НаимПолн', 'Не указан')
                customer_inn = data['Заказчик'][0].get('ИНН', 'Не указан')
                customer_address = data['Заказчик'][0].get('АдресПолн', 'Не указан')

            # Предмет закупки
            subject = data.get('Продукт', {}).get('Название', 'Не указан')

            # Цена
            price_info = data.get('НачЦена', {})
            price = price_info.get('Сумма', 'Не указана')
            currency = price_info.get('ВалютаНаим', '₽')
            if price != 'Не указана' and price:
                price = f"{price} {currency}"

            # Даты
            publication_date = data.get('ДатаПубл', 'Не указана')
            submission_deadline = data.get('ДатаОконч', 'Не указана')

            # Статус
            status = data.get('Статус', {})
            if isinstance(status, dict):
                status = status.get('Статус', 'Не указан')
            elif isinstance(status, str):
                pass  # уже строка
            else:
                status = 'Не указан'

            # Документы
            documents = data.get('Документы', [])
            doc_count = len(documents) if documents else 0

            # Дополнительная информация
            procurement_type = data.get('СпособРазм', 'Не указан')  # Используем СпособРазм вместо ТипЗакупки
            procurement_method = data.get('СпособРазм', 'Не указан')
            delivery_place = data.get('МестоПостав', 'Не указано')  # Используем МестоПостав
            delivery_terms = data.get('СрокПостав', 'Не указан')  # Используем СрокПостав
            
            # Обеспечение заявки
            application_guarantee = data.get('ОбеспУчаст', {})
            guarantee_amount = application_guarantee.get('Сумма', 'Не указана') if application_guarantee else 'Не указана'
            
            # Источник финансирования (может отсутствовать в API)
            funding_source = 'Не указан'  # Это поле может отсутствовать в DaMIA API
            
            # Региональная информация
            region = data.get('Регион', 'Не указан')
            federal_law = data.get('ФЗ', 'Не указан')
            
            # Электронная торговая площадка
            etp_info = data.get('ЭТП', {})
            etp_name = etp_info.get('Наименование', 'Не указана') if etp_info else 'Не указана'
            etp_url = etp_info.get('Url', 'Не указан') if etp_info else 'Не указан'
            
            # Контактная информация
            contacts = data.get('Контакты', {})
            contact_person = contacts.get('ОтвЛицо', 'Не указано') if contacts else 'Не указано'
            contact_phone = contacts.get('Телефон', 'Не указан') if contacts else 'Не указан'
            contact_email = contacts.get('Email', 'Не указан') if contacts else 'Не указан'
            
            # Финансовые детали
            ikz = data.get('ИКЗ', 'Не указан')
            advance_percent = data.get('АвансПроцент', 'Не указан')
            
            # Обеспечение исполнения контракта
            execution_guarantee = data.get('ОбеспИсп', {})
            execution_amount = execution_guarantee.get('Сумма', 'Не указана') if execution_guarantee else 'Не указана'
            
            # Банковское сопровождение
            bank_support = data.get('БанкСопр', 'Не указано')

            return {
                'customer': customer or 'Не указан',
                'customer_inn': customer_inn or 'Не указан',
                'customer_address': customer_address or 'Не указан',
                'subject': subject or 'Не указан',
                'price': price or 'Не указана',
                'publication_date': publication_date or 'Не указана',
                'submission_deadline': submission_deadline or 'Не указана',
                'status': status or 'Не указан',
                'document_count': doc_count,
                'procurement_type': procurement_type or 'Не указан',
                'procurement_method': procurement_method or 'Не указан',
                'delivery_place': delivery_place or 'Не указано',
                'delivery_terms': delivery_terms or 'Не указан',
                'guarantee_amount': guarantee_amount or 'Не указана',
                'funding_source': funding_source or 'Не указан',
                'region': region or 'Не указан',
                'federal_law': federal_law or 'Не указан',
                'etp_name': etp_name or 'Не указана',
                'etp_url': etp_url or 'Не указан',
                'contact_person': contact_person or 'Не указано',
                'contact_phone': contact_phone or 'Не указан',
                'contact_email': contact_email or 'Не указан',
                'ikz': ikz or 'Не указан',
                'advance_percent': advance_percent or 'Не указан',
                'execution_amount': execution_amount or 'Не указана',
                'bank_support': bank_support or 'Не указано',
                'raw_data': data
            }
        except Exception as e:
            logger.error(f"[damia] ❌ Ошибка форматирования данных: {e}")
            return {
                'customer': 'Ошибка обработки',
                'customer_inn': 'Ошибка обработки',
                'customer_address': 'Ошибка обработки',
                'subject': 'Ошибка обработки',
                'price': 'Ошибка обработки',
                'publication_date': 'Ошибка обработки',
                'submission_deadline': 'Ошибка обработки',
                'status': 'Ошибка обработки',
                'document_count': 0,
                'procurement_type': 'Ошибка обработки',
                'procurement_method': 'Ошибка обработки',
                'delivery_place': 'Ошибка обработки',
                'delivery_terms': 'Ошибка обработки',
                'guarantee_amount': 'Ошибка обработки',
                'funding_source': 'Ошибка обработки',
                'region': 'Ошибка обработки',
                'federal_law': 'Ошибка обработки',
                'etp_name': 'Ошибка обработки',
                'etp_url': 'Ошибка обработки',
                'contact_person': 'Ошибка обработки',
                'contact_phone': 'Ошибка обработки',
                'contact_email': 'Ошибка обработки',
                'ikz': 'Ошибка обработки',
                'advance_percent': 'Ошибка обработки',
                'execution_amount': 'Ошибка обработки',
                'bank_support': 'Ошибка обработки',
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
