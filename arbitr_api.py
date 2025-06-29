"""
DaMIA API обертка для арбитражных дел
Проверка арбитражных дел через API-Арбитражи
"""

import httpx
import asyncio
import logging
from typing import Dict, List, Optional
from config import DAMIA_ARBITR_API_KEY, DAMIA_ARBITR_BASE_URL

logger = logging.getLogger(__name__)

class DamiaArbitrAPI:
    """Класс для работы с DaMIA API для арбитражных дел"""
    
    # Константы для ролей в арбитражных делах
    ROLE_PLAINTIFF = '1'      # Истец
    ROLE_DEFENDANT = '2'      # Ответчик
    ROLE_THIRD_PARTY = '3'    # Третье лицо
    ROLE_OTHER = '4'          # Иное лицо
    
    # Константы для типов арбитражных дел
    TYPE_ADMINISTRATIVE = '1'  # Административное
    TYPE_CIVIL = '2'          # Гражданское
    TYPE_BANKRUPTCY = '3'     # Банкротное
    
    # Константы для статусов арбитражных дел
    STATUS_COMPLETED = '1'     # Рассмотрение дела завершено
    STATUS_FIRST_INSTANCE = '2'  # Рассматривается в первой инстанции
    STATUS_APPEAL = '3'       # Рассматривается в апелляционной/кассационной/надзорной инстанциях
    
    def __init__(self):
        self.api_key = DAMIA_ARBITR_API_KEY
        self.base_url = DAMIA_ARBITR_BASE_URL
        self.timeout = 30.0
        self.max_retries = 3
        self.retry_delay = 1.0
    
    async def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Выполняет запрос к API с повторными попытками"""
        # API-Арбитражи не требует специальных заголовков, только параметры
        
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    url = f"{self.base_url}/{endpoint}"
                    response = await client.get(url, params=params)
                    
                    logger.info(f"[arbitr] Запрос к {url} с параметрами {params}")
                    logger.info(f"[arbitr] Статус ответа: {response.status_code}")
                    logger.info(f"[arbitr] Текст ответа: {response.text[:500]}...")
                    
                    if response.status_code == 200:
                        try:
                            result = response.json()
                            logger.info(f"[arbitr] Успешный ответ для {endpoint}: {result}")
                            return result
                        except Exception as e:
                            logger.error(f"[arbitr] Ошибка парсинга JSON для {endpoint}: {e}")
                            logger.error(f"[arbitr] Текст ответа: {response.text}")
                            return None
                    elif response.status_code == 404:
                        logger.warning(f"[arbitr] Данные не найдены для {endpoint}: {params}")
                        return None
                    else:
                        logger.error(f"[arbitr] Ошибка API {endpoint}: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[arbitr] Таймаут при запросе {endpoint} (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[arbitr] Ошибка при запросе {endpoint}: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return None
    
    async def get_arbitrage_case(self, case_number: str) -> Dict:
        """
        Получение информации об арбитражном деле по номеру
        Метод: delo
        """
        logger.info(f"[arbitr] Получение информации об арбитражном деле: {case_number}")
        
        params = {
            'regn': case_number,
            'key': self.api_key
        }
        
        result = await self._make_request('delo', params)
        
        if result:
            return {
                "case_number": case_number,
                "data": result,
                "status": "found"
            }
        
        return {
            "case_number": case_number,
            "data": None,
            "status": "not_found"
        }
    
    async def get_arbitrage_cases_by_inn(self, inn: str, role: Optional[str] = None, case_type: Optional[str] = None, 
                                       status: Optional[str] = None, format_type: int = 1, exact: bool = True,
                                       from_date: Optional[str] = None, to_date: Optional[str] = None,
                                       page: int = 1) -> Dict:
        """
        Получение информации об участиях в арбитражных делах по ИНН
        Метод: dela
        
        Параметры:
        - inn: ИНН, ОГРН, название организации или ФИО
        - role: Роль лица (1-Истец, 2-Ответчик, 3-Третье лицо, 4-Иное лицо)
        - case_type: Тип дела (1-Административное, 2-Гражданское, 3-Банкротное)
        - status: Статус дела (1-Завершено, 2-Первая инстанция, 3-Апелляция/Кассация)
        - format_type: Формат данных (1-группированные, 2-негруппированные)
        - exact: Точное совпадение (True/False)
        - from_date: Дата начала поиска (YYYY-MM-DD)
        - to_date: Дата окончания поиска (YYYY-MM-DD)
        - page: Номер страницы
        """
        logger.info(f"[arbitr] Поиск арбитражных дел для ИНН: {inn}")
        
        params = {
            'q': inn,
            'format': format_type,
            'exact': '1' if exact else '0',
            'page': str(page),
            'key': self.api_key
        }
        
        # Добавляем дополнительные параметры если переданы
        if role:
            params['role'] = role
        if case_type:
            params['type'] = case_type
        if status:
            params['status'] = status
        if from_date:
            params['from_date'] = from_date
        if to_date:
            params['to_date'] = to_date
        
        result = await self._make_request('dela', params)
        
        logger.info(f"[arbitr] Результат поиска дел для {inn}: {result}")
        
        if result and isinstance(result, dict):
            # Обрабатываем данные в зависимости от формата
            if format_type == 1:  # группированные данные
                result_data = result.get('result', {})
                cases = []
                total_count = 0
                
                # Извлекаем дела из группированной структуры
                for role, years_data in result_data.items():
                    if isinstance(years_data, dict):
                        for year, year_data in years_data.items():
                            if isinstance(year_data, dict):
                                # Подсчитываем дела в этом году
                                for decision_type, decisions in year_data.items():
                                    if isinstance(decisions, dict):
                                        total_count += len(decisions)
                                        # Добавляем дела в список
                                        for case_number, case_data in decisions.items():
                                            if isinstance(case_data, dict):
                                                case_info = {
                                                    'case_number': case_number,
                                                    'role': role,
                                                    'year': year,
                                                    'case_type': case_data.get('Тип', 'Неизвестно'),
                                                    'status': case_data.get('Статус', 'Неизвестно'),
                                                    'court': case_data.get('Суд', 'Неизвестно'),
                                                    'amount': case_data.get('Сумма', 0),
                                                    'date': case_data.get('Дата', 'Неизвестно')
                                                }
                                                cases.append(case_info)
                
                return {
                    "inn": inn,
                    "cases": cases,
                    "total_count": total_count,
                    "has_next_page": False,  # В группированном формате нет пагинации
                    "status": "found"
                }
            else:  # негруппированные данные (format=2)
                result_data = result.get('result', {})
                cases = []
                total_count = result.get('count', 0)
                has_next_page = result.get('next_page', False)
                
                # Извлекаем дела из негруппированной структуры
                for role, role_cases in result_data.items():
                    if isinstance(role_cases, dict):
                        for case_number, case_data in role_cases.items():
                            if isinstance(case_data, dict):
                                case_info = {
                                    'case_number': case_number,
                                    'role': role,
                                    'case_type': case_data.get('Тип', 'Неизвестно'),
                                    'status': case_data.get('Статус', 'Неизвестно'),
                                    'court': case_data.get('Суд', 'Неизвестно'),
                                    'amount': case_data.get('Сумма', 0),
                                    'date': case_data.get('Дата', 'Неизвестно'),
                                    'judge': case_data.get('Судья', 'Неизвестно'),
                                    'url': case_data.get('Url', ''),
                                    'match_type': case_data.get('Совпадение', 'Неизвестно')
                                }
                                cases.append(case_info)
                
                return {
                    "inn": inn,
                    "cases": cases,
                    "total_count": total_count,
                    "has_next_page": has_next_page,
                    "status": "found"
                }
        elif result and isinstance(result, str):
            logger.warning(f"[arbitr] API вернул строку вместо JSON для {inn}: {result}")
            return {
                "inn": inn,
                "cases": [],
                "total_count": 0,
                "has_next_page": False,
                "status": "error",
                "error": f"API вернул неверный формат: {result}"
            }
        
        return {
            "inn": inn,
            "cases": [],
            "total_count": 0,
            "has_next_page": False,
            "status": "not_found"
        }
    
    async def track_arbitrage_case(self, case_number: str, action: str = 'email', 
                                 email: Optional[str] = None) -> Dict:
        """
        Отслеживание событий в арбитражном деле
        Метод: delopro
        
        Действия:
        - email: получать извещения об изменениях по делу на электронную почту
        - noemail: отписаться от получения извещений об изменениях по делу на email
        - list: получить список отслеживаемых дел
        """
        logger.info(f"[arbitr] Отслеживание арбитражного дела: {case_number}")
        
        params = {
            'a': action,
            'key': self.api_key
        }
        
        # Добавляем номер дела только если это не запрос списка
        if action != 'list':
            params['regn'] = case_number
        
        # Добавляем email если передан
        if email:
            params['email'] = email
        
        result = await self._make_request('delopro', params)
        
        if result:
            return {
                "case_number": case_number if action != 'list' else None,
                "action": action,
                "data": result,
                "status": "success"
            }
        
        return {
            "case_number": case_number if action != 'list' else None,
            "action": action,
            "data": None,
            "status": "failed"
        }
    
    async def get_tracked_cases(self) -> Dict:
        """
        Получение списка отслеживаемых арбитражных дел
        Метод: delopro с параметром a=list
        """
        logger.info("[arbitr] Получение списка отслеживаемых дел")
        
        params = {
            'a': 'list',
            'key': self.api_key
        }
        
        result = await self._make_request('delopro', params)
        
        if result:
            return {
                "tracked_cases": result,
                "status": "success"
            }
        
        return {
            "tracked_cases": [],
            "status": "failed"
        }
    
    def format_arbitrage_summary(self, cases_data: Dict) -> str:
        """Форматирует сводку по арбитражным делам"""
        if not cases_data or cases_data.get('status') != 'found':
            return "Арбитражные дела не найдены"
        
        cases = cases_data.get('cases', [])
        total_count = cases_data.get('total_count', 0)
        
        if not cases:
            return "Арбитражные дела не найдены"
        
        summary = f"📋 Найдено арбитражных дел: {total_count}\n\n"
        
        # Группируем по ролям
        roles = {
            '1': 'Истец',
            '2': 'Ответчик', 
            '3': 'Третье лицо',
            '4': 'Иное лицо'
        }
        
        role_counts = {}
        for case in cases:
            role = case.get('role', '4')
            role_counts[role] = role_counts.get(role, 0) + 1
        
        for role_code, role_name in roles.items():
            if role_code in role_counts:
                summary += f"• {role_name}: {role_counts[role_code]} дел\n"
        
        # Добавляем последние дела
        summary += "\n📄 Последние дела:\n"
        for i, case in enumerate(cases[:5], 1):
            case_number = case.get('case_number', 'Неизвестно')
            case_type = case.get('case_type', 'Неизвестно')
            status = case.get('status', 'Неизвестно')
            summary += f"{i}. {case_number} ({case_type}) - {status}\n"
        
        return summary

# Создаем глобальный экземпляр
arbitr_api = DamiaArbitrAPI() 