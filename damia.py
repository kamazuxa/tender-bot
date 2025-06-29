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

# Retry настройки - ВРЕМЕННО ОТКЛЮЧЕНО
MAX_RETRIES = 1  # Уменьшаем до 1 попытки
RETRY_DELAY = 0  # Убираем задержки

def retry_on_error(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """Декоратор для retry-логики - ВРЕМЕННО УПРОЩЕН"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"[damia] Ошибка API: {e}")
                raise e
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
        logger.info(f"[damia] Отправляем запрос к {url} с параметрами: {params}")
        
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            logger.info(f"[damia] zakupka для {reg_number}: статус {resp.status_code}")
            logger.info(f"[damia] Заголовки ответа: {dict(resp.headers)}")
            logger.info(f"[damia] Полный ответ: {resp.text}")
            
            if resp.status_code == 200 and resp.text.strip():
                try:
                    data = resp.json()
                    logger.info(f"[damia] zakupka ответ (JSON): {data}")
                    return data
                except json.JSONDecodeError:
                    # Если ответ не JSON, проверяем на ошибки
                    response_text = resp.text.strip()
                    logger.info(f"[damia] zakupka ответ (не JSON): {response_text}")
                    if "Ошибка:" in response_text or "ошибка" in response_text.lower():
                        logger.error(f"[damia] API вернул ошибку: {response_text}")
                        raise DamiaAPIError(f"API error: {response_text}")
                    raise DamiaAPIError(f"Invalid JSON response: {response_text}")
            else:
                logger.info(f"[damia] zakupka пустой ответ или ошибка: {resp.text[:200]}")
        return None
    
    @retry_on_error()
    async def get_contract(self, reg_number: str) -> Optional[Dict]:
        url = f"https://api.damia.ru/zakupki/contract"
        params = {"regn": reg_number, "key": self.api_key}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, params=params)
            logger.info(f"[damia] contract для {reg_number}: статус {resp.status_code}")
            if resp.status_code == 200 and resp.text.strip():
                try:
                    data = resp.json()
                    logger.info(f"[damia] contract ответ: {data}")
                    return data
                except json.JSONDecodeError:
                    # Если ответ не JSON, проверяем на ошибки
                    response_text = resp.text.strip()
                    logger.info(f"[damia] contract ответ (не JSON): {response_text}")
                    if "Ошибка:" in response_text or "ошибка" in response_text.lower():
                        logger.error(f"[damia] API вернул ошибку: {response_text}")
                        raise DamiaAPIError(f"API error: {response_text}")
                    raise DamiaAPIError(f"Invalid JSON response: {response_text}")
            else:
                logger.info(f"[damia] contract пустой ответ или ошибка: {resp.text[:200]}")
        return None
    
    @retry_on_error()
    async def zsearch(self, q: str, **kwargs) -> Optional[Dict]:
        """Поиск тендеров по запросу согласно документации DaMIA API"""
        # Основной URL поиска согласно документации
        url = "https://damia.ru/api-zakupki/zsearch"
        
        # Базовые параметры поиска
        params = {
            "q": q,
            "key": self.api_key
        }
        
        # Добавляем дополнительные параметры если переданы
        params.update(kwargs)
        
        try:
            # Используем правильные заголовки для API
            headers = {
                "User-Agent": "TenderBot/1.0",
                "Accept": "application/json",
                "Content-Type": "application/json"
            }
            
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                logger.info(f"[damia] Поиск по запросу: {q}")
                resp = await client.get(url, params=params, headers=headers)
                logger.info(f"[damia] Статус ответа: {resp.status_code}")
                
                if resp.status_code == 200:
                    if resp.text.strip():
                        try:
                            data = resp.json()
                            logger.info(f"[damia] Получены данные поиска: {len(str(data))} символов")
                            logger.info(f"[damia] Содержимое ответа: {data}")
                            return data
                        except json.JSONDecodeError as e:
                            logger.error(f"[damia] Ошибка парсинга JSON: {e}")
                            logger.error(f"[damia] Ответ сервера: {resp.text[:500]}")
                            return None
                    else:
                        logger.warning(f"[damia] Пустой ответ от сервера")
                        return None
                elif resp.status_code == 301 or resp.status_code == 302:
                    logger.warning(f"[damia] Получен редирект {resp.status_code}")
                    redirect_url = resp.headers.get('Location')
                    if redirect_url:
                        logger.info(f"[damia] Следуем редиректу на: {redirect_url}")
                        redirect_resp = await client.get(redirect_url, headers=headers)
                        if redirect_resp.status_code == 200 and redirect_resp.text.strip():
                            try:
                                data = redirect_resp.json()
                                return data
                            except json.JSONDecodeError:
                                logger.error(f"[damia] Ошибка парсинга JSON после редиректа")
                                return None
                else:
                    logger.error(f"[damia] Ошибка API: {resp.status_code} - {resp.text[:200]}")
                    return None
                    
        except httpx.TimeoutException:
            logger.error(f"[damia] Таймаут при поиске: {q}")
            return None
        except httpx.RequestError as e:
            logger.error(f"[damia] Ошибка сети при поиске: {e}")
            return None
        except Exception as e:
            logger.error(f"[damia] Неожиданная ошибка при поиске: {e}")
            return None
        
        return None
    
    @retry_on_error()
    async def get_tender_info(self, reg_number: str) -> Optional[Dict]:
        """
        Получает информацию о тендере по регистрационному номеру
        Пробует разные эндпоинты для поиска данных согласно документации DaMIA API
        """
        logger.info(f"[damia] Поиск тендера {reg_number}")
        
        # Сначала пробуем zakupka, потом contract
        data = await self.get_zakupka(reg_number)
        if data and not self._is_empty_response(data):
            logger.info(f"[damia] Тендер {reg_number} найден через zakupka")
            return data
            
        data = await self.get_contract(reg_number)
        if data and not self._is_empty_response(data):
            logger.info(f"[damia] Тендер {reg_number} найден через contract")
            return data
            
        # Если не нашли, пробуем поиск по номеру с разными стратегиями
        logger.warning(f"[damia] Тендер {reg_number} не найден в основных эндпоинтах, пробуем поиск")
        
        # Пробуем разные варианты поиска согласно документации API
        search_strategies = [
            # Прямой поиск по номеру
            {"q": reg_number},
            
            # Поиск с символом номера
            {"q": f"№{reg_number}"},
            
            # Поиск с ключевыми словами
            {"q": f"тендер {reg_number}"},
            {"q": f"закупка {reg_number}"},
            
            # Поиск с ограничением по датам (последние 2 года)
            {"q": reg_number, "from_date": "2022-01-01"},
            {"q": reg_number, "to_date": "2024-12-31"},
            
            # Поиск по разным ФЗ
            {"q": reg_number, "fz": 44},
            {"q": reg_number, "fz": 223},
            
            # Поиск с разными статусами
            {"q": reg_number, "status": 1},  # Подача заявок
            {"q": reg_number, "status": 2},  # Работа комиссии
            {"q": reg_number, "status": 3},  # Закупка завершена
        ]
        
        for strategy in search_strategies:
            try:
                search_data = await self.zsearch(**strategy)
                if search_data and not self._is_empty_response(search_data):
                    logger.info(f"[damia] Тендер {reg_number} найден через поиск с параметрами: {strategy}")
                    return search_data
            except Exception as e:
                logger.warning(f"[damia] Ошибка при поиске с параметрами {strategy}: {e}")
                continue
        
        # Последняя попытка - пробуем альтернативные эндпоинты
        logger.warning(f"[damia] Пробуем альтернативные эндпоинты для тендера {reg_number}")
        alt_data = await self._try_alternative_endpoints(reg_number)
        if alt_data:
            return alt_data
        
        logger.error(f"[damia] Тендер {reg_number} не найден ни в одном эндпоинте")
        return None
    
    async def _try_alternative_endpoints(self, reg_number: str) -> Optional[Dict]:
        """Пробует альтернативные эндпоинты для получения данных тендера"""
        alternative_urls = [
            f"https://api.damia.ru/zakupki/tender/{reg_number}",
            f"https://api.damia.ru/tender/{reg_number}",
            f"https://api.damia.ru/zakupki/info/{reg_number}",
            f"https://api.damia.ru/info/{reg_number}"
        ]
        
        for url in alternative_urls:
            try:
                params = {"key": self.api_key}
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                    resp = await client.get(url, params=params)
                    logger.info(f"[damia] Альтернативный эндпоинт {url}: статус {resp.status_code}")
                    
                    if resp.status_code == 200 and resp.text.strip():
                        data = resp.json()
                        if data and not self._is_empty_response(data):
                            logger.info(f"[damia] Тендер найден через альтернативный эндпоинт: {url}")
                            return data
            except Exception as e:
                logger.warning(f"[damia] Ошибка при обращении к альтернативному эндпоинту {url}: {e}")
                continue
        
        return None
    
    async def test_api_connection(self) -> bool:
        """Проверяет доступность DaMIA API"""
        try:
            # Пробуем простой запрос к API
            test_url = "https://api.damia.ru/zakupki/zakupka"
            params = {"regn": "0373200193019000001", "key": self.api_key}
            
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(test_url, params=params)
                logger.info(f"[damia] Тест API: статус {resp.status_code}")
                return resp.status_code in [200, 404]  # 404 тоже нормально - значит API работает
        except Exception as e:
            logger.error(f"[damia] Ошибка при тестировании API: {e}")
            return False
    
    def _is_empty_response(self, data: Dict) -> bool:
        """Проверяет, является ли ответ пустым или неинформативным"""
        if not data:
            logger.info(f"[damia] Ответ пустой (None или пустой dict)")
            return True
        
        # Логируем структуру ответа для отладки
        logger.info(f"[damia] Структура ответа: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        
        # Если это поисковый результат, проверяем другие поля
        if 'ФЗ' in data:
            # Это результат поиска, проверяем наличие данных
            # Считаем ответ непустым, если есть хотя бы одно из основных полей
            main_fields = ['РазмОрг', 'Продукт', 'НачЦена', 'Заказчик', 'Статус', 'Контакты', 'Документы']
            has_main_data = any(field in data for field in main_fields)
            
            logger.info(f"[damia] Поисковый результат с ФЗ: {data}, пустой: {not has_main_data}")
            return not has_main_data
        
        # Проверяем основные поля, которые должны быть в ответе
        required_fields = ['РазмОрг', 'Продукт', 'НачЦена', 'Заказчик', 'Статус']
        has_required = any(field in data for field in required_fields)
        
        logger.info(f"[damia] Проверка обязательных полей: {has_required}, найденные поля: {[k for k in data.keys() if k in required_fields]}")
        
        # Если есть хотя бы одно обязательное поле, считаем ответ непустым
        if has_required:
            return False
        
        # Если нет обязательных полей, но есть другие данные, тоже считаем непустым
        # (возможно, API изменил структуру ответа)
        if len(data) > 0:
            logger.info(f"[damia] Ответ содержит данные, но не стандартные поля: {data}")
            return False
        
        logger.info(f"[damia] Ответ действительно пустой")
        return True
    
    def extract_tender_number(self, text: str) -> Optional[str]:
        """
        Извлекает номер тендера из текста (ссылка или номер)
        Поддерживает различные форматы включая тендеры по 223-ФЗ
        """
        import re
        
        # Сначала проверяем специальные случаи для 223-ФЗ
        # Для ссылок вида: https://zakupki.gov.ru/epz/order/notice/notice223/common-info.html?noticeInfoId=18488839
        # Нужно извлекать правильный номер тендера, а не noticeInfoId
        
        # Паттерн для 223-ФЗ с noticeInfoId
        fz223_pattern = r'zakupki\.gov\.ru/epz/order/notice/notice223/common-info\.html\?noticeInfoId=(\d+)'
        fz223_match = re.search(fz223_pattern, text)
        if fz223_match:
            notice_info_id = fz223_match.group(1)
            logger.info(f"[damia] Найден noticeInfoId для 223-ФЗ: {notice_info_id}")
            
            # Для 223-ФЗ ищем полный регистрационный номер в тексте
            # Поддерживаем номера разной длины (10-20 цифр)
            full_number_pattern = r'\b\d{10,20}\b'
            full_matches = re.findall(full_number_pattern, text)
            
            if full_matches:
                # Берем первый найденный полный номер
                full_number = full_matches[0]
                logger.info(f"[damia] Найден полный номер тендера 223-ФЗ: {full_number}")
                return full_number
            else:
                # Если полный номер не найден, возвращаем noticeInfoId
                # но добавляем предупреждение в лог
                logger.warning(f"[damia] Для 223-ФЗ найден только noticeInfoId: {notice_info_id}. Полный номер не найден в тексте.")
                return notice_info_id
        
        # Паттерны для поиска номеров тендеров (поддерживаем разную длину)
        patterns = [
            r'\b\d{10}\b',  # 10-значный номер (как 9703074147)
            r'\b\d{11}\b',  # 11-значный номер (как 32514989413)
            r'\b\d{12}\b',  # 12-значный номер
            r'\b\d{13}\b',  # 13-значный номер
            r'\b\d{14}\b',  # 14-значный номер
            r'\b\d{15}\b',  # 15-значный номер
            r'\b\d{16}\b',  # 16-значный номер
            r'\b\d{17}\b',  # 17-значный номер
            r'\b\d{18}\b',  # 18-значный номер
            r'\b\d{19}\b',  # 19-значный номер
            r'\b\d{20}\b',  # 20-значный номер
            r'zakupki\.gov\.ru/epz/order/notice/.*?(\d{10,20})',  # Ссылка на госзакупки с номером
            r'zakupki\.gov\.ru/.*?(\d{10,20})',  # Общая ссылка на госзакупки с номером
            r'regNumber=(\d+)',  # Формат с regNumber
            r'orderId=(\d+)',  # Формат с orderId
            r'zakupki\.gov\.ru/epz/order/notice/ea44/common-info\.html\?regNumber=(\d+)',  # Формат 44-ФЗ
            r'noticeInfoId=(\d+)',  # Общий формат с noticeInfoId (если не 223-ФЗ)
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                extracted = match.group(1) if len(match.groups()) > 0 else match.group(0)
                logger.info(f"[damia] Извлечен номер тендера: {extracted}")
                return extracted
        
        logger.warning(f"[damia] Не удалось извлечь номер тендера из текста: {text[:100]}...")
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
