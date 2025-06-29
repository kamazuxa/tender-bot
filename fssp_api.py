"""
FSSP API Client для проверки исполнительных производств
Интеграция с API-ФССП через платформу DaMIA
"""

import aiohttp
import logging
from typing import Dict, Optional, Any, List
from config import FSSP_API_KEY

logger = logging.getLogger(__name__)

class FSSPAPIClient:
    """Клиент для работы с FSSP API через DaMIA"""
    
    def __init__(self):
        self.api_key = FSSP_API_KEY
        self.base_url = "https://api.damia.ru/fssp"
        self.session = None
    
    async def _get_session(self):
        """Получает или создает aiohttp сессию"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Закрывает сессию"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_executive_proceeding_ul(self, regn: str) -> Optional[Dict[str, Any]]:
        """
        Информация об исполнительном производстве ЮЛ (isp)
        
        Args:
            regn: Номер исполнительного производства (индивидуального или сводного)
            
        Returns:
            Dict с информацией об исполнительном производстве или None при ошибке
        """
        try:
            session = await self._get_session()
            
            params = {
                'regn': regn,
                'key': self.api_key
            }
            
            async with session.get(
                f"{self.base_url}/isp",
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"[FSSP] Успешное получение информации о производстве {regn}")
                    return self._format_isp_result(data)
                else:
                    logger.error(f"[FSSP] Ошибка API isp: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"[FSSP] Ошибка при получении информации о производстве {regn}: {e}")
            return None
    
    async def get_company_proceedings(self, inn: str, from_date: Optional[str] = None, 
                                    to_date: Optional[str] = None, format: int = 2, 
                                    page: int = 1) -> Optional[Dict[str, Any]]:
        """
        Информация об участиях ЮЛ в исполнительных производствах (isps)
        
        Args:
            inn: ИНН организации
            from_date: Дата возбуждения после (YYYY-MM-DD)
            to_date: Дата возбуждения до (YYYY-MM-DD)
            format: Тип формата (1 - группированный, 2 - негруппированный)
            page: Номер страницы
            
        Returns:
            Dict с информацией об исполнительных производствах или None при ошибке
        """
        try:
            session = await self._get_session()
            
            params = {
                'inn': inn,
                'format': format,
                'page': page,
                'key': self.api_key
            }
            
            if from_date:
                params['from_date'] = from_date
            if to_date:
                params['to_date'] = to_date
            
            async with session.get(
                f"{self.base_url}/isps",
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"[FSSP] Успешное получение производств для ИНН {inn}")
                    return self._format_isps_result(data, format)
                else:
                    logger.error(f"[FSSP] Ошибка API isps: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"[FSSP] Ошибка при получении производств для ИНН {inn}: {e}")
            return None
    
    async def get_executive_proceeding_fl(self, regn: str) -> Optional[Dict[str, Any]]:
        """
        Информация об исполнительном производстве ФЛ (ispfl)
        
        Args:
            regn: Номер исполнительного производства (индивидуального)
            
        Returns:
            Dict с информацией об исполнительном производстве или None при ошибке
        """
        try:
            session = await self._get_session()
            
            params = {
                'regn': regn,
                'key': self.api_key
            }
            
            async with session.get(
                f"{self.base_url}/ispfl",
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"[FSSP] Успешное получение информации о производстве ФЛ {regn}")
                    return self._format_ispfl_result(data)
                else:
                    logger.error(f"[FSSP] Ошибка API ispfl: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"[FSSP] Ошибка при получении информации о производстве ФЛ {regn}: {e}")
            return None
    
    async def get_person_proceedings(self, fam: str, nam: str, otch: Optional[str] = None,
                                   bdate: Optional[str] = None, region: Optional[int] = None,
                                   format: int = 2, page: int = 1) -> Optional[Dict[str, Any]]:
        """
        Информация об участиях ФЛ в исполнительных производствах (ispsfl)
        
        Args:
            fam: Фамилия должника
            nam: Имя должника
            otch: Отчество должника (необязательно)
            bdate: Дата рождения в формате DD.MM.YYYY (необязательно)
            region: Код региона отдела судебных приставов (необязательно)
            format: Тип формата (1 - группированный, 2 - негруппированный)
            page: Номер страницы
            
        Returns:
            Dict с информацией об исполнительных производствах или None при ошибке
        """
        try:
            session = await self._get_session()
            
            params = {
                'fam': fam,
                'nam': nam,
                'format': format,
                'page': page,
                'key': self.api_key
            }
            
            if otch:
                params['otch'] = otch
            if bdate:
                params['bdate'] = bdate
            if region:
                params['region'] = region
            
            async with session.get(
                f"{self.base_url}/ispsfl",
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"[FSSP] Успешное получение производств для ФЛ {fam} {nam}")
                    return self._format_ispsfl_result(data, format)
                else:
                    logger.error(f"[FSSP] Ошибка API ispsfl: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"[FSSP] Ошибка при получении производств для ФЛ {fam} {nam}: {e}")
            return None
    
    def _format_isp_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Форматирует результат метода isp"""
        try:
            return {
                'status': 'success',
                'method': 'isp',
                'data': data,
                'regn': data.get('РегНомер', 'Не указано')
            }
        except Exception as e:
            logger.error(f"[FSSP] Ошибка форматирования результата isp: {e}")
            return {
                'status': 'error',
                'method': 'isp',
                'message': f'Ошибка форматирования: {str(e)}'
            }
    
    def _format_isps_result(self, data: Dict[str, Any], format: int) -> Dict[str, Any]:
        """Форматирует результат метода isps"""
        try:
            result = {
                'status': 'success',
                'method': 'isps',
                'format': format,
                'data': data
            }
            
            # В API-ФССП данные возвращаются в виде словаря с ИНН как ключом
            # Извлекаем ИНН из ключей данных
            if isinstance(data, dict):
                inn_keys = [key for key in data.keys() if key.isdigit() and len(key) in [10, 12]]
                if inn_keys:
                    result['inn'] = inn_keys[0]
                else:
                    result['inn'] = 'Не указано'
            else:
                result['inn'] = 'Не указано'
            
            return result
        except Exception as e:
            logger.error(f"[FSSP] Ошибка форматирования результата isps: {e}")
            return {
                'status': 'error',
                'method': 'isps',
                'message': f'Ошибка форматирования: {str(e)}'
            }
    
    def _format_ispfl_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Форматирует результат метода ispfl"""
        try:
            return {
                'status': 'success',
                'method': 'ispfl',
                'data': data,
                'result': data.get('result', {})
            }
        except Exception as e:
            logger.error(f"[FSSP] Ошибка форматирования результата ispfl: {e}")
            return {
                'status': 'error',
                'method': 'ispfl',
                'message': f'Ошибка форматирования: {str(e)}'
            }
    
    def _format_ispsfl_result(self, data: Dict[str, Any], format: int) -> Dict[str, Any]:
        """Форматирует результат метода ispsfl"""
        try:
            result = {
                'status': 'success',
                'method': 'ispsfl',
                'format': format,
                'data': data
            }
            
            if format == 1:  # группированные данные
                result['result'] = data.get('result', {})
            else:  # негруппированные данные
                result['result'] = data.get('result', {})
            
            return result
        except Exception as e:
            logger.error(f"[FSSP] Ошибка форматирования результата ispsfl: {e}")
            return {
                'status': 'error',
                'method': 'ispsfl',
                'message': f'Ошибка форматирования: {str(e)}'
            }
    
    async def check_company(self, inn: str) -> Optional[Dict[str, Any]]:
        """
        Проверка компании по ИНН (обертка для get_company_proceedings)
        
        Args:
            inn: ИНН организации
            
        Returns:
            Dict с информацией о компании и исполнительных производствах
        """
        try:
            logger.info(f"[FSSP] Проверка компании по ИНН {inn}")
            
            # Получаем исполнительные производства
            proceedings_data = await self.get_company_proceedings(inn)
            logger.info(f"[FSSP] Результат get_company_proceedings для {inn}: {proceedings_data}")
            
            if not proceedings_data:
                return {
                    'status': 'error',
                    'error': 'Не удалось получить данные ФССП'
                }
            
            # Формируем результат в нужном формате
            result = {
                'status': 'success',
                'company_info': {
                    'inn': inn,
                    'name': 'Не указано',  # ФССП API не возвращает название компании
                    'ogrn': 'Не указано',  # ФССП API не возвращает ОГРН
                    'address': 'Не указано'  # ФССП API не возвращает адрес
                },
                'executive_proceedings': [],
                'summary': {
                    'total_proceedings': 0,
                    'active_proceedings': 0,
                    'total_debt': 0
                }
            }
            
            # Обрабатываем данные о производствах
            if proceedings_data.get('status') == 'success':
                data = proceedings_data.get('data', {})
                logger.info(f"[FSSP] Данные о производствах для {inn}: {data}")
                
                # Извлекаем информацию о производствах
                proceedings = []
                total_debt = 0
                active_count = 0
                
                # Обрабатываем данные в зависимости от формата
                if isinstance(data, dict):
                    # Ищем данные по ИНН
                    inn_data = data.get(inn, {})
                    if isinstance(inn_data, dict):
                        # Обрабатываем группированные данные (format=1)
                        for year, year_data in inn_data.items():
                            if isinstance(year_data, dict):
                                # Обрабатываем статусы: Завершено, Погашено, Не завершено
                                for status_type, status_data in year_data.items():
                                    if isinstance(status_data, dict):
                                        # Обрабатываем типы задолженности
                                        for debt_type, debt_data in status_data.items():
                                            if isinstance(debt_data, dict):
                                                # Получаем список ИП
                                                ip_list = debt_data.get('ИП', [])
                                                amount = debt_data.get('Сумма', 0)
                                                count = debt_data.get('Количество', 0)
                                                
                                                # Подсчитываем общую задолженность
                                                if isinstance(amount, (int, float)) and amount > 0:
                                                    total_debt += amount
                                                
                                                # Подсчитываем активные производства
                                                if status_type == 'Не завершено':
                                                    active_count += count
                                                
                                                # Добавляем каждое производство в список
                                                for ip_number in ip_list:
                                                    proc_info = {
                                                        'number': ip_number,
                                                        'amount': amount,
                                                        'status': status_type,
                                                        'year': year,
                                                        'debt_type': debt_type,
                                                        'date': f"{year}",
                                                        'court': 'Не указано',
                                                        'bailiff': 'Не указано'
                                                    }
                                                    proceedings.append(proc_info)
                    elif isinstance(inn_data, list):
                        # Обрабатываем негруппированные данные (format=2)
                        for proc in inn_data:
                            if isinstance(proc, dict):
                                proc_info = {
                                    'number': proc.get('РегНомерИП', proc.get('number', 'Не указано')),
                                    'amount': proc.get('Сумма', proc.get('amount', 0)),
                                    'status': proc.get('Статус', proc.get('status', 'Не указано')),
                                    'date': proc.get('Дата', proc.get('date', 'Не указано')),
                                    'court': proc.get('ДепНаим', proc.get('court', 'Не указано')),
                                    'bailiff': proc.get('Пристав', proc.get('bailiff', 'Не указано')),
                                    'subject': proc.get('Предмет', 'Не указано'),
                                    'debtor': proc.get('Должник', {})
                                }
                                
                                # Подсчитываем общую задолженность
                                amount = proc.get('Сумма', proc.get('amount', 0))
                                if isinstance(amount, (int, float)) and amount > 0:
                                    total_debt += amount
                                
                                # Подсчитываем активные производства
                                status = proc.get('Статус', proc.get('status', '')).lower()
                                if 'не завершено' in status or 'актив' in status or 'исполн' in status:
                                    active_count += 1
                                
                                proceedings.append(proc_info)
                
                logger.info(f"[FSSP] Найдено производств для {inn}: {len(proceedings)}")
                
                result['executive_proceedings'] = proceedings
                result['summary'] = {
                    'total_proceedings': len(proceedings),
                    'active_proceedings': active_count,
                    'total_debt': total_debt
                }
                
                # Если нет производств, пытаемся получить данные о компании из других источников
                if len(proceedings) == 0:
                    logger.info(f"[FSSP] Нет производств для {inn}, пытаемся получить данные о компании")
                    # Здесь можно добавить запрос к ФНС API для получения данных о компании
                    # Пока оставляем как есть, но добавляем флаг
                    result['no_proceedings'] = True
                    result['company_info']['note'] = 'Данные о компании не доступны в ФССП (нет производств)'
            
            logger.info(f"[FSSP] Проверка завершена для ИНН {inn}")
            return result
            
        except Exception as e:
            logger.error(f"[FSSP] Ошибка при проверке компании {inn}: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    async def test_connection(self) -> bool:
        """
        Проверяет доступность API
        
        Returns:
            True если API доступен, False иначе
        """
        try:
            session = await self._get_session()
            
            # Тестируем простой запрос
            params = {
                'inn': '7728898960',  # Тестовый ИНН
                'key': self.api_key
            }
            
            async with session.get(
                f"{self.base_url}/isps",
                params=params
            ) as response:
                return response.status == 200
                
        except Exception as e:
            logger.error(f"[FSSP] Ошибка проверки соединения: {e}")
            return False

# Создаем глобальный экземпляр клиента
fssp_client = FSSPAPIClient() 