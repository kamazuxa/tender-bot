"""
API ФНС обертка для работы с ЕГРЮЛ/ЕГРИП
Проверка компаний через API-ФНС
"""

import httpx
import asyncio
import logging
from typing import Dict, List, Optional
from config import FNS_API_KEY

logger = logging.getLogger(__name__)

class FNSAPI:
    """Класс для работы с API ФНС"""
    
    def __init__(self):
        self.api_key = FNS_API_KEY
        self.base_url = "https://api-fns.ru/api"
        self.timeout = 30.0
        self.max_retries = 3
        self.retry_delay = 1.0
    
    async def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Выполняет запрос к API ФНС с повторными попытками"""
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = f"{self.base_url}/{endpoint}"
                    response = await client.get(url, params=params)
                    
                    logger.info(f"[fns] Запрос к {url} с параметрами {params}")
                    logger.info(f"[fns] Статус ответа: {response.status_code}")
                    
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"[fns] Успешный ответ: {result}")
                        return result
                    elif response.status_code == 404:
                        logger.warning(f"[fns] Данные не найдены для {endpoint}: {params}")
                        return None
                    elif response.status_code == 403:
                        logger.error(f"[fns] Доступ запрещен (403): {response.text}")
                        logger.error(f"[fns] Проверьте API ключ и IP-адрес в личном кабинете https://api-fns.ru")
                        return None
                    else:
                        logger.error(f"[fns] Ошибка API {endpoint}: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[fns] Таймаут при запросе {endpoint} (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[fns] Ошибка при запросе {endpoint}: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return None
    
    async def search_companies(self, query: str, page: int = 1) -> Dict:
        """
        Поиск компаний по запросу
        Метод: search
        """
        logger.info(f"[fns] Поиск компаний: {query}")
        
        params = {
            'q': query,
            'key': self.api_key
        }
        
        if page > 1:
            params['page'] = str(page)
        
        result = await self._make_request('search', params)
        
        if result:
            return {
                "query": query,
                "companies": result.get('items', []),
                "total_count": result.get('Count', 0),
                "status": "found"
            }
        
        return {
            "query": query,
            "companies": [],
            "total_count": 0,
            "status": "not_found"
        }
    
    async def get_company_info(self, inn_or_ogrn: str) -> Dict:
        """
        Получение данных о компании из ЕГРЮЛ/ЕГРИП
        Метод: egr
        """
        logger.info(f"[fns] Получение данных компании: {inn_or_ogrn}")
        
        params = {
            'req': inn_or_ogrn,
            'key': self.api_key
        }
        
        result = await self._make_request('egr', params)
        logger.info(f"[fns] Результат get_company_info для {inn_or_ogrn}: {result}")
        
        if result and result.get('items'):
            return {
                "inn_or_ogrn": inn_or_ogrn,
                "data": result.get('items', []),
                "status": "found"
            }
        
        return {
            "inn_or_ogrn": inn_or_ogrn,
            "data": [],
            "status": "not_found"
        }
    
    async def check_company(self, inn_or_ogrn: str) -> Dict:
        """
        Проверка контрагента (признаки недобросовестности)
        Метод: check
        """
        logger.info(f"[fns] Проверка контрагента: {inn_or_ogrn}")
        
        params = {
            'req': inn_or_ogrn,
            'key': self.api_key
        }
        
        result = await self._make_request('check', params)
        logger.info(f"[fns] Результат check_company для {inn_or_ogrn}: {result}")
        
        if result and result.get('items'):
            items = result.get('items', [])
            if items:
                item = items[0]
                # Определяем тип организации (ЮЛ или ИП)
                if 'ЮЛ' in item:
                    company_data = item['ЮЛ']
                    company_type = 'ЮЛ'
                elif 'ИП' in item:
                    company_data = item['ИП']
                    company_type = 'ИП'
                else:
                    company_data = {}
                    company_type = 'Неизвестно'
                
                positive = company_data.get('Позитив', {})
                negative = company_data.get('Негатив', {})
                
                return {
                    "inn_or_ogrn": inn_or_ogrn,
                    "company_type": company_type,
                    "has_violations": bool(negative),
                    "positive_factors": positive,
                    "negative_factors": negative,
                    "status": "found",
                    "raw_data": result
                }
        
        return {
            "inn_or_ogrn": inn_or_ogrn,
            "company_type": "Неизвестно",
            "has_violations": False,
            "positive_factors": {},
            "negative_factors": {},
            "status": "not_found",
            "raw_data": None
        }
    
    async def get_company_changes(self, inn_or_ogrn: str, from_date: Optional[str] = None) -> Dict:
        """
        Отслеживание изменений параметров компании
        Метод: changes
        """
        logger.info(f"[fns] Получение изменений компании {inn_or_ogrn} с {from_date}")
        
        params = {
            'req': inn_or_ogrn,
            'key': self.api_key
        }
        
        if from_date:
            params['dat'] = from_date
        
        result = await self._make_request('changes', params)
        
        if result and result.get('items'):
            return {
                "inn_or_ogrn": inn_or_ogrn,
                "from_date": from_date,
                "changes": result.get('items', []),
                "status": "found"
            }
        
        return {
            "inn_or_ogrn": inn_or_ogrn,
            "from_date": from_date,
            "changes": [],
            "status": "not_found"
        }
    
    async def check_account_blocks(self, inn: str) -> Dict:
        """
        Проверка блокировок счета
        Метод: nalogbi
        """
        logger.info(f"[fns] Проверка блокировок счета: {inn}")
        
        params = {
            'inn': inn,
            'key': self.api_key
        }
        
        result = await self._make_request('nalogbi', params)
        
        if result and result.get('items'):
            return {
                "inn": inn,
                "blocks_data": result.get('items', []),
                "status": "found"
            }
        
        return {
            "inn": inn,
            "blocks_data": [],
            "status": "not_found"
        }
    
    def format_company_info(self, company_data: Dict) -> str:
        """Форматирует информацию о компании для вывода"""
        if not company_data or company_data.get('status') != 'found':
            return "❌ Данные компании не найдены"
        
        items = company_data.get('data', [])
        if not items:
            return "❌ Данные компании не найдены"
        
        # Берем первую найденную компанию
        item = items[0]
        
        # Определяем тип организации
        if 'ЮЛ' in item:
            company = item['ЮЛ']
            company_type = "Юридическое лицо"
        elif 'ИП' in item:
            company = item['ИП']
            company_type = "Индивидуальный предприниматель"
        elif 'НР' in item:
            company = item['НР']
            company_type = "Представительство иностранной компании"
        else:
            return "❌ Неизвестный тип организации"
        
        # Формируем информацию
        info = f"🏢 **{company_type}**\n\n"
        
        # Основная информация
        if company_type == "Юридическое лицо":
            info += f"**Наименование:** {company.get('НаимСокрЮЛ', 'Не указано')}\n"
            info += f"**Полное наименование:** {company.get('НаимПолнЮЛ', 'Не указано')}\n"
        elif company_type == "Индивидуальный предприниматель":
            info += f"**ФИО:** {company.get('ФИОПолн', 'Не указано')}\n"
        
        info += f"**ИНН:** {company.get('ИНН', company.get('ИННФЛ', 'Не указано'))}\n"
        info += f"**ОГРН:** {company.get('ОГРН', company.get('ОГРНИП', 'Не указано'))}\n"
        info += f"**Статус:** {company.get('Статус', 'Не указано')}\n"
        info += f"**Дата регистрации:** {company.get('ДатаРег', 'Не указано')}\n"
        
        if company.get('ДатаПрекр'):
            info += f"**Дата прекращения:** {company.get('ДатаПрекр')}\n"
        
        info += f"**Адрес:** {company.get('АдресПолн', 'Не указано')}\n"
        info += f"**Основной вид деятельности:** {company.get('ОснВидДеят', 'Не указано')}\n"
        
        # Контактная информация
        if company.get('НомТел'):
            info += f"**Телефон:** {company.get('НомТел')}\n"
        
        if company.get('E-mail'):
            info += f"**Email:** {company.get('E-mail')}\n"
        
        # Руководитель (для ЮЛ)
        if company_type == "Юридическое лицо" and company.get('Руководитель'):
            director = company['Руководитель']
            info += f"**Руководитель:** {director.get('ФИОПолн', 'Не указано')}\n"
            info += f"**Должность:** {director.get('Должн', 'Не указано')}\n"
        
        # Учредители (для ЮЛ)
        if company_type == "Юридическое лицо" and company.get('Учредители'):
            founders = company['Учредители']
            info += f"**Учредители:** {len(founders)} чел.\n"
            for i, founder in enumerate(founders[:3], 1):  # Показываем первых 3
                if 'УчрФЛ' in founder:
                    founder_info = founder['УчрФЛ']
                    info += f"  {i}. {founder_info.get('ФИОПолн', 'Не указано')} - {founder.get('Процент', '0')}%\n"
                elif 'УчрЮЛ' in founder:
                    founder_info = founder['УчрЮЛ']
                    info += f"  {i}. {founder_info.get('НаимСокрЮЛ', 'Не указано')} - {founder.get('Процент', '0')}%\n"
        
        return info
    
    def format_company_check(self, check_data: Dict) -> str:
        """Форматирует результаты проверки контрагента"""
        if not check_data or check_data.get('status') != 'found':
            return "❌ Данные проверки не найдены"
        
        info = f"🔍 **Результаты проверки контрагента**\n\n"
        info += f"**Тип организации:** {check_data.get('company_type', 'Неизвестно')}\n"
        
        positive = check_data.get('positive_factors', {})
        negative = check_data.get('negative_factors', {})
        
        if positive:
            info += "\n✅ **Позитивные факторы:**\n"
            if positive.get('Текст'):
                info += f"• {positive['Текст']}\n"
            else:
                for key, value in positive.items():
                    if key != 'Текст':
                        info += f"• {key}: {value}\n"
        
        if negative:
            info += "\n❌ **Негативные факторы:**\n"
            if negative.get('Текст'):
                info += f"• {negative['Текст']}\n"
            else:
                for key, value in negative.items():
                    if key != 'Текст':
                        info += f"• {key}: {value}\n"
        
        if not positive and not negative:
            info += "\n✅ **Признаков недобросовестности не обнаружено**\n"
        
        return info

# Создаем глобальный экземпляр
fns_api = FNSAPI() 