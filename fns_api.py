"""
DaMIA API обертка для ФНС (ЕГРЮЛ/ЕГРИП)
Проверка компаний через API-ФНС
"""

import httpx
import asyncio
import logging
from typing import Dict, List, Optional
from config import DAMIA_FNS_API_KEY, DAMIA_FNS_BASE_URL

logger = logging.getLogger(__name__)

class DamiaFNSAPI:
    """Класс для работы с DaMIA API для ФНС"""
    
    def __init__(self):
        self.api_key = DAMIA_FNS_API_KEY
        self.base_url = DAMIA_FNS_BASE_URL
        self.timeout = 30.0
        self.max_retries = 3
        self.retry_delay = 1.0
    
    async def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Выполняет запрос к API с повторными попытками"""
        headers = {
            "User-Agent": "TenderBot/1.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = f"{self.base_url}/{endpoint}"
                    response = await client.get(url, headers=headers, params=params)
                    
                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 404:
                        logger.warning(f"[fns] Данные не найдены для {endpoint}: {params}")
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
    
    async def search_companies(self, query: str, limit: int = 10) -> Dict:
        """
        Поиск компаний по запросу
        Метод: search
        """
        logger.info(f"[fns] Поиск компаний: {query}")
        
        params = {
            'q': query,
            'key': self.api_key
        }
        
        if limit:
            params['limit'] = str(limit)
        
        result = await self._make_request('search', params)
        
        if result:
            return {
                "query": query,
                "companies": result.get('items', []),
                "total_count": result.get('count', 0),
                "status": "found"
            }
        
        return {
            "query": query,
            "companies": [],
            "total_count": 0,
            "status": "not_found"
        }
    
    async def get_company_info(self, inn: str) -> Dict:
        """
        Получение данных о компании из ЕГРЮЛ/ЕГРИП
        Метод: egr
        """
        logger.info(f"[fns] Получение данных компании: {inn}")
        
        params = {
            'req': inn,
            'key': self.api_key
        }
        
        result = await self._make_request('egr', params)
        
        if result:
            return {
                "inn": inn,
                "data": result,
                "status": "found"
            }
        
        return {
            "inn": inn,
            "data": None,
            "status": "not_found"
        }
    
    async def check_company(self, inn: str) -> Dict:
        """
        Проверка контрагента (признаки недобросовестности)
        Метод: check
        """
        logger.info(f"[fns] Проверка контрагента: {inn}")
        
        params = {
            'req': inn,
            'key': self.api_key
        }
        
        result = await self._make_request('check', params)
        
        if result:
            return {
                "inn": inn,
                "has_violations": result.get("has_violations", False),
                "violations_count": result.get("violations_count", 0),
                "last_check_date": result.get("last_check_date"),
                "status": result.get("status", "unknown"),
                "negative_registers": result.get("negative_registers", []),
                "mass_director": result.get("mass_director", False),
                "mass_founder": result.get("mass_founder", False),
                "liquidation": result.get("liquidation", False),
                "reorganization": result.get("reorganization", False),
                "unreliable_data": result.get("unreliable_data", False),
                "raw_data": result
            }
        
        return {
            "inn": inn,
            "has_violations": False,
            "violations_count": 0,
            "last_check_date": None,
            "status": "not_found",
            "negative_registers": [],
            "mass_director": False,
            "mass_founder": False,
            "liquidation": False,
            "reorganization": False,
            "unreliable_data": False,
            "raw_data": None
        }
    
    async def get_company_changes(self, inn: str, from_date: str) -> Dict:
        """
        Отслеживание изменений параметров компании
        Метод: changes
        """
        logger.info(f"[fns] Получение изменений компании {inn} с {from_date}")
        
        params = {
            'req': inn,
            'from_date': from_date,
            'key': self.api_key
        }
        
        result = await self._make_request('changes', params)
        
        if result:
            return {
                "inn": inn,
                "from_date": from_date,
                "changes": result.get('changes', []),
                "status": "found"
            }
        
        return {
            "inn": inn,
            "from_date": from_date,
            "changes": [],
            "status": "not_found"
        }
    
    async def get_inn_by_passport(self, passport_series: str, passport_number: str) -> Dict:
        """
        Получение ИНН физического лица по паспортным данным
        Метод: innfl
        """
        logger.info(f"[fns] Поиск ИНН по паспорту: {passport_series} {passport_number}")
        
        params = {
            'series': passport_series,
            'number': passport_number,
            'key': self.api_key
        }
        
        result = await self._make_request('innfl', params)
        
        if result:
            return {
                "passport": f"{passport_series} {passport_number}",
                "inn": result.get('inn'),
                "status": "found"
            }
        
        return {
            "passport": f"{passport_series} {passport_number}",
            "inn": None,
            "status": "not_found"
        }
    
    async def check_passport_validity(self, passport_series: str, passport_number: str) -> Dict:
        """
        Проверка паспорта на недействительность
        Метод: mvdpass
        """
        logger.info(f"[fns] Проверка паспорта: {passport_series} {passport_number}")
        
        params = {
            'series': passport_series,
            'number': passport_number,
            'key': self.api_key
        }
        
        result = await self._make_request('mvdpass', params)
        
        if result:
            return {
                "passport": f"{passport_series} {passport_number}",
                "is_valid": result.get('is_valid', True),
                "status": "found"
            }
        
        return {
            "passport": f"{passport_series} {passport_number}",
            "is_valid": True,
            "status": "not_found"
        }
    
    def format_company_summary(self, company_data: Dict) -> str:
        """Форматирует сводку по компании"""
        if not company_data or company_data.get('status') != 'found':
            return "Данные компании не найдены"
        
        data = company_data.get('data', {})
        
        summary = f"🏢 {data.get('name', 'Неизвестно')}\n"
        summary += f"ИНН: {data.get('inn', 'Неизвестно')}\n"
        summary += f"ОГРН: {data.get('ogrn', 'Неизвестно')}\n"
        summary += f"Статус: {data.get('status', 'Неизвестно')}\n"
        summary += f"Адрес: {data.get('address', 'Неизвестно')}\n"
        summary += f"Директор: {data.get('director', 'Неизвестно')}\n"
        summary += f"Дата регистрации: {data.get('registration_date', 'Неизвестно')}\n"
        
        return summary

# Создаем глобальный экземпляр
fns_api = DamiaFNSAPI() 