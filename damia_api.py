"""
DaMIA API обертка для проверки поставщиков
Проверка через ФНС, ФССП, Арбитраж, Скоринг
"""

import httpx
import asyncio
import logging
from typing import Dict, List, Optional
from config import DAMIA_SUPPLIER_API_KEY, DAMIA_SUPPLIER_BASE_URL

logger = logging.getLogger(__name__)

class DamiaSupplierAPI:
    """Класс для работы с DaMIA API для проверки поставщиков"""
    
    def __init__(self):
        self.api_key = DAMIA_SUPPLIER_API_KEY
        self.base_url = DAMIA_SUPPLIER_BASE_URL
        self.fns_api_url = 'https://api-fns.ru/api/'
        self.timeout = 30.0
        self.max_retries = 3
        self.retry_delay = 1.0
    
    async def _make_request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Выполняет запрос к API с повторными попытками"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
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
                        logger.warning(f"[damia] Данные не найдены для {endpoint}: {params}")
                        return None
                    else:
                        logger.error(f"[damia] Ошибка API {endpoint}: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[damia] Таймаут при запросе {endpoint} (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[damia] Ошибка при запросе {endpoint}: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return None
    
    async def _make_fns_request(self, method: str, inn: str) -> Optional[Dict]:
        """Выполняет запрос к API ФНС"""
        params = {
            'req': inn,
            'key': self.api_key
        }
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = f"{self.fns_api_url}{method}"
                    response = await client.get(url, params=params)
                    
                    if response.status_code == 200:
                        return response.json()
                    else:
                        logger.error(f"[damia] Ошибка API ФНС {method}: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[damia] Таймаут при запросе ФНС {method} (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[damia] Ошибка при запросе ФНС {method}: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return None
    
    async def get_fns(self, inn: str) -> Dict:
        """
        Проверка через ФНС (налоговая служба)
        Использует метод 'check' для проверки контрагента
        """
        logger.info(f"[damia] Проверка ФНС для ИНН: {inn}")
        
        result = await self._make_fns_request('check', inn)
        
        if result:
            # Парсим ответ API ФНС
            return {
                "has_violations": result.get("has_violations", False),
                "violations_count": result.get("violations_count", 0),
                "last_check_date": result.get("last_check_date"),
                "status": result.get("status", "unknown"),
                "negative_registers": result.get("negative_registers", []),
                "mass_director": result.get("mass_director", False),
                "mass_founder": result.get("mass_founder", False),
                "liquidation": result.get("liquidation", False),
                "reorganization": result.get("reorganization", False),
                "unreliable_data": result.get("unreliable_data", False)
            }
        
        return {
            "has_violations": False,
            "violations_count": 0,
            "last_check_date": None,
            "status": "not_found",
            "negative_registers": [],
            "mass_director": False,
            "mass_founder": False,
            "liquidation": False,
            "reorganization": False,
            "unreliable_data": False
        }
    
    async def get_egr_info(self, inn: str) -> Dict:
        """
        Получение данных из ЕГРЮЛ/ЕГРИП
        Использует метод 'egr' для получения актуальных данных
        """
        logger.info(f"[damia] Получение ЕГР данных для ИНН: {inn}")
        
        result = await self._make_fns_request('egr', inn)
        
        if result:
            # Парсим ответ API ФНС ЕГР
            return {
                "company_name": result.get("name", ""),
                "legal_address": result.get("address", ""),
                "registration_date": result.get("registration_date"),
                "status": result.get("status", "unknown"),
                "director": result.get("director", ""),
                "founders": result.get("founders", []),
                "activities": result.get("activities", []),
                "authorized_capital": result.get("authorized_capital"),
                "tax_authority": result.get("tax_authority", "")
            }
        
        return {
            "company_name": "",
            "legal_address": "",
            "registration_date": None,
            "status": "not_found",
            "director": "",
            "founders": [],
            "activities": [],
            "authorized_capital": None,
            "tax_authority": ""
        }
    
    async def get_fssp(self, inn: str) -> Dict:
        """
        Проверка через ФССП (судебные приставы)
        Использует метод 'isps' для получения информации об участиях ЮЛ в исполнительных производствах
        """
        logger.info(f"[damia] Проверка ФССП для ИНН: {inn}")
        
        params = {
            'inn': inn,
            'format': '1',  # Группированные данные
            'key': self.api_key
        }
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = "https://api.damia.ru/fssp/isps"
                    response = await client.get(url, params=params)
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        # Парсим ответ API ФССП
                        if result and inn in result:
                            fssp_data = result[inn]
                            
                            # Подсчитываем статистику
                            total_cases = 0
                            active_cases = 0
                            total_debt_amount = 0
                            
                            if isinstance(fssp_data, dict):
                                # Группированные данные
                                for year, year_cases in fssp_data.items():
                                    if isinstance(year_cases, list):
                                        total_cases += len(year_cases)
                                        for case in year_cases:
                                            if isinstance(case, dict):
                                                # Проверяем статус дела
                                                status = case.get('status', '').lower()
                                                if 'действует' in status or 'активно' in status:
                                                    active_cases += 1
                                                
                                                # Суммируем задолженность
                                                debt_amount = case.get('debt_amount', 0)
                                                if isinstance(debt_amount, (int, float)):
                                                    total_debt_amount += debt_amount
                            elif isinstance(fssp_data, list):
                                # Негруппированные данные
                                total_cases = len(fssp_data)
                                for case in fssp_data:
                                    if isinstance(case, dict):
                                        status = case.get('status', '').lower()
                                        if 'действует' in status or 'активно' in status:
                                            active_cases += 1
                                        
                                        debt_amount = case.get('debt_amount', 0)
                                        if isinstance(debt_amount, (int, float)):
                                            total_debt_amount += debt_amount
                            
                            return {
                                "has_debts": total_cases > 0,
                                "debts_count": total_cases,
                                "active_cases": active_cases,
                                "total_debt_amount": total_debt_amount,
                                "last_update": None,  # TODO: добавить дату обновления
                                "cases": fssp_data
                            }
                        else:
                            logger.warning(f"[damia] Данные ФССП не найдены для ИНН: {inn}")
                            return {
                                "has_debts": False,
                                "debts_count": 0,
                                "active_cases": 0,
                                "total_debt_amount": 0,
                                "last_update": None,
                                "cases": []
                            }
                    else:
                        logger.error(f"[damia] Ошибка API ФССП: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[damia] Таймаут при запросе ФССП (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[damia] Ошибка при запросе ФССП: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return {
            "has_debts": False,
            "debts_count": 0,
            "active_cases": 0,
            "total_debt_amount": 0,
            "last_update": None,
            "cases": []
        }
    
    async def get_fssp_case_details(self, case_number: str) -> Dict:
        """
        Получение детальной информации об исполнительном производстве
        Использует метод 'isp' для получения информации по номеру производства
        """
        logger.info(f"[damia] Получение деталей исполнительного производства: {case_number}")
        
        params = {
            'regn': case_number,
            'key': self.api_key
        }
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = "https://api.damia.ru/fssp/isp"
                    response = await client.get(url, params=params)
                    
                    if response.status_code == 200:
                        result = response.json()
                        return result
                    else:
                        logger.error(f"[damia] Ошибка API ФССП isp: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[damia] Таймаут при запросе деталей ФССП (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[damia] Ошибка при запросе деталей ФССП: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return {}
    
    async def get_arbitr(self, inn: str) -> List:
        """
        Проверка через Арбитражный суд
        Использует метод 'dela' для получения информации об участиях в арбитражных делах
        """
        logger.info(f"[damia] Проверка Арбитража для ИНН: {inn}")
        
        params = {
            'q': inn,
            'format': '1',  # Группированные данные
            'key': self.api_key
        }
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = "https://api.damia.ru/arb/dela"
                    response = await client.get(url, params=params)
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        # Парсим ответ API Арбитража
                        if result and 'result' in result:
                            cases = result['result']
                            if isinstance(cases, list):
                                return cases
                            elif isinstance(cases, dict):
                                # Если результат в виде словаря, извлекаем дела
                                all_cases = []
                                for case_data in cases.values():
                                    if isinstance(case_data, list):
                                        all_cases.extend(case_data)
                                    elif isinstance(case_data, dict):
                                        all_cases.append(case_data)
                                return all_cases
                        return []
                    else:
                        logger.error(f"[damia] Ошибка API Арбитража: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[damia] Таймаут при запросе Арбитража (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[damia] Ошибка при запросе Арбитража: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return []
    
    async def get_arbitr_case_details(self, case_number: str) -> Dict:
        """
        Получение детальной информации об арбитражном деле
        Использует метод 'delo' для получения информации по номеру дела
        """
        logger.info(f"[damia] Получение деталей арбитражного дела: {case_number}")
        
        params = {
            'regn': case_number,
            'key': self.api_key
        }
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = "https://api.damia.ru/arb/delo"
                    response = await client.get(url, params=params)
                    
                    if response.status_code == 200:
                        result = response.json()
                        return result
                    else:
                        logger.error(f"[damia] Ошибка API Арбитража delo: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[damia] Таймаут при запросе деталей дела (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[damia] Ошибка при запросе деталей дела: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return {}
    
    async def get_scoring(self, inn: str) -> Dict:
        """
        Получение скоринговой оценки компании
        Использует API Скоринг для расчета рисков контрагента
        """
        logger.info(f"[damia] Получение скоринга для ИНН: {inn}")
        
        # Используем модель _problemCredit для оценки проблемных кредитов
        params = {
            'inn': inn,
            'model': '_problemCredit',
            'key': self.api_key
        }
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = "https://damia.ru/api-scoring/score"
                    response = await client.get(url, params=params)
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        # Парсим ответ API Скоринг
                        if result and inn in result:
                            score_data = result[inn]
                            
                            # Извлекаем скоринговую оценку
                            score_value = None
                            risk_level = "Неизвестно"
                            
                            if isinstance(score_data, dict):
                                # Ищем скоринговую оценку в различных полях
                                for key, value in score_data.items():
                                    if isinstance(value, (int, float)) and 0 <= value <= 1000:
                                        score_value = value
                                        break
                                
                                # Определяем уровень риска по скорингу
                                if score_value is not None:
                                    if score_value >= 800:
                                        risk_level = "Низкий"
                                    elif score_value >= 600:
                                        risk_level = "Средний"
                                    elif score_value >= 400:
                                        risk_level = "Высокий"
                                    else:
                                        risk_level = "Критический"
                            
                            return {
                                "score": score_value,
                                "risk_level": risk_level,
                                "model": "_problemCredit",
                                "raw_data": score_data
                            }
                        else:
                            logger.warning(f"[damia] Данные скоринга не найдены для ИНН: {inn}")
                            return {
                                "score": None,
                                "risk_level": "Неизвестно",
                                "model": "_problemCredit",
                                "raw_data": {}
                            }
                    else:
                        logger.error(f"[damia] Ошибка API Скоринг: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[damia] Таймаут при запросе скоринга (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[damia] Ошибка при запросе скоринга: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return {
            "score": None,
            "risk_level": "Неизвестно",
            "model": "_problemCredit",
            "raw_data": {}
        }
    
    async def get_financial_coefficients(self, inn: str) -> Dict:
        """
        Получение финансовых коэффициентов компании
        Использует API Скоринг для получения финансовых показателей
        """
        logger.info(f"[damia] Получение финансовых коэффициентов для ИНН: {inn}")
        
        params = {
            'inn': inn,
            'key': self.api_key
        }
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = "https://damia.ru/api-scoring/fincoefs"
                    response = await client.get(url, params=params)
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        # Парсим ответ API Скоринг
                        if result and inn in result:
                            fin_data = result[inn]
                            return {
                                "coefficients": fin_data,
                                "inn": inn
                            }
                        else:
                            logger.warning(f"[damia] Финансовые коэффициенты не найдены для ИНН: {inn}")
                            return {
                                "coefficients": {},
                                "inn": inn
                            }
                    else:
                        logger.error(f"[damia] Ошибка API Скоринг fincoefs: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[damia] Таймаут при запросе финансовых коэффициентов (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[damia] Ошибка при запросе финансовых коэффициентов: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return {
            "coefficients": {},
            "inn": inn
        }
    
    async def search_tenders(self, search_params: Dict) -> List[Dict]:
        """
        Поиск тендеров по параметрам
        """
        logger.info(f"[damia] Поиск тендеров с параметрами: {search_params}")
        
        # Формируем параметры запроса
        params = {
            'key': self.api_key,
            'limit': search_params.get('limit', 50)
        }
        
        # Добавляем поисковые параметры
        if 'query' in search_params:
            params['query'] = search_params['query']
        if 'date_from' in search_params:
            params['date_from'] = search_params['date_from']
        if 'date_to' in search_params:
            params['date_to'] = search_params['date_to']
        if 'region' in search_params:
            params['region'] = search_params['region']
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    # Используем эндпоинт поиска тендеров
                    url = "https://api.damia.ru/tenders/search"
                    response = await client.get(url, params=params)
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        # Парсим результат поиска
                        if isinstance(result, dict) and 'tenders' in result:
                            tenders = result['tenders']
                        elif isinstance(result, list):
                            tenders = result
                        else:
                            tenders = []
                        
                        logger.info(f"[damia] Найдено {len(tenders)} тендеров")
                        return tenders
                    else:
                        logger.error(f"[damia] Ошибка поиска тендеров: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[damia] Таймаут при поиске тендеров (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[damia] Ошибка при поиске тендеров: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return []

# Глобальный экземпляр для использования в других модулях
damia_supplier_api = DamiaSupplierAPI() 