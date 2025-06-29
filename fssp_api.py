"""
FSSP API Client для проверки исполнительных производств
"""

import aiohttp
import logging
from typing import Dict, Optional, Any
from config import FSSP_API_KEY, FSSP_BASE_URL

logger = logging.getLogger(__name__)

class FSSPAPIClient:
    """Клиент для работы с FSSP API"""
    
    def __init__(self):
        self.api_key = FSSP_API_KEY
        self.base_url = FSSP_BASE_URL
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
    
    async def check_company(self, inn: str) -> Optional[Dict[str, Any]]:
        """
        Проверяет компанию по ИНН в базе ФССП
        
        Args:
            inn: ИНН компании
            
        Returns:
            Dict с результатами проверки или None при ошибке
        """
        try:
            session = await self._get_session()
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            params = {
                'inn': inn,
                'type': 'ul'  # юридическое лицо
            }
            
            async with session.get(
                f"{self.base_url}/search",
                headers=headers,
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"[FSSP] Успешная проверка ИНН {inn}")
                    return self._format_result(data)
                else:
                    logger.error(f"[FSSP] Ошибка API: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"[FSSP] Ошибка при проверке ИНН {inn}: {e}")
            return None
    
    def _format_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Форматирует результат проверки ФССП
        
        Args:
            data: Сырые данные от API
            
        Returns:
            Отформатированный результат
        """
        try:
            result = {
                'status': 'success',
                'company_info': {},
                'executive_proceedings': [],
                'summary': {
                    'total_proceedings': 0,
                    'active_proceedings': 0,
                    'total_debt': 0
                }
            }
            
            # Извлекаем информацию о компании
            if 'company' in data:
                company = data['company']
                result['company_info'] = {
                    'name': company.get('name', 'Не указано'),
                    'inn': company.get('inn', 'Не указано'),
                    'ogrn': company.get('ogrn', 'Не указано'),
                    'address': company.get('address', 'Не указано')
                }
            
            # Извлекаем исполнительные производства
            if 'proceedings' in data:
                proceedings = data['proceedings']
                result['executive_proceedings'] = []
                
                for proc in proceedings:
                    proceeding = {
                        'number': proc.get('number', 'Не указано'),
                        'date': proc.get('date', 'Не указано'),
                        'amount': proc.get('amount', 0),
                        'status': proc.get('status', 'Не указано'),
                        'bailiff': proc.get('bailiff', 'Не указано'),
                        'department': proc.get('department', 'Не указано')
                    }
                    result['executive_proceedings'].append(proceeding)
                    
                    # Обновляем сводку
                    result['summary']['total_proceedings'] += 1
                    if proc.get('status') == 'active':
                        result['summary']['active_proceedings'] += 1
                    result['summary']['total_debt'] += proc.get('amount', 0)
            
            return result
            
        except Exception as e:
            logger.error(f"[FSSP] Ошибка форматирования результата: {e}")
            return {
                'status': 'error',
                'message': f'Ошибка форматирования: {str(e)}'
            }
    
    async def test_connection(self) -> bool:
        """
        Проверяет доступность API
        
        Returns:
            True если API доступен, False иначе
        """
        try:
            session = await self._get_session()
            
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            async with session.get(
                f"{self.base_url}/status",
                headers=headers
            ) as response:
                return response.status == 200
                
        except Exception as e:
            logger.error(f"[FSSP] Ошибка проверки соединения: {e}")
            return False

# Создаем глобальный экземпляр клиента
fssp_client = FSSPAPIClient() 