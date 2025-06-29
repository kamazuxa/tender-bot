"""
DaMIA API обертка для скоринга
Расчет рисков контрагентов через API-Скоринг
"""

import httpx
import asyncio
import logging
from typing import Dict, List, Optional
from config import DAMIA_SCORING_API_KEY, DAMIA_SCORING_BASE_URL

logger = logging.getLogger(__name__)

class DamiaScoringAPI:
    """Класс для работы с DaMIA API для скоринга"""
    
    def __init__(self):
        self.api_key = DAMIA_SCORING_API_KEY
        self.base_url = DAMIA_SCORING_BASE_URL
        self.timeout = 30.0
        self.max_retries = 3
        self.retry_delay = 1.0
        
        # Доступные скоринговые модели
        self.available_models = {
            '_bankrots2016': 'Скоринг компаний-банкротов',
            '_tech': 'Скоринг компаний по "черному списку" 115-ФЗ',
            '_diskf': 'Скоринг компаний дисквалифицированных лиц',
            '_problemCredit': 'Скоринг компаний с проблемными кредитами',
            '_zsk': 'Скоринг рискованной деятельности компаний (антиотмывочное законодательство)'
        }
    
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
                        logger.warning(f"[scoring] Данные не найдены для {endpoint}: {params}")
                        return None
                    else:
                        logger.error(f"[scoring] Ошибка API {endpoint}: {response.status_code} - {response.text}")
                        
            except httpx.TimeoutException:
                logger.warning(f"[scoring] Таймаут при запросе {endpoint} (попытка {attempt + 1})")
            except Exception as e:
                logger.error(f"[scoring] Ошибка при запросе {endpoint}: {e}")
            
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        return None
    
    async def calculate_risk_score(self, inn: str, model: str = '_problemCredit', 
                                 balance_data: Optional[Dict] = None) -> Dict:
        """
        Расчет рисков контрагента
        Метод: score
        """
        logger.info(f"[scoring] Расчет рисков для ИНН {inn} с моделью {model}")
        
        params = {
            'inn': inn,
            'model': model,
            'key': self.api_key
        }
        
        # Добавляем балансовые данные если переданы
        if balance_data:
            for code, value in balance_data.items():
                if isinstance(code, str) and code.startswith('b'):
                    params[code] = str(value)
        
        result = await self._make_request('score', params)
        
        if result:
            return {
                "inn": inn,
                "model": model,
                "score": result.get('score', 0),
                "risk_level": result.get('risk_level', 'unknown'),
                "probability": result.get('probability', 0),
                "factors": result.get('factors', []),
                "raw_data": result,
                "status": "success"
            }
        
        return {
            "inn": inn,
            "model": model,
            "score": 0,
            "risk_level": "unknown",
            "probability": 0,
            "factors": [],
            "raw_data": None,
            "status": "failed"
        }
    
    async def get_model_info(self, model: str) -> Dict:
        """
        Информация о скоринговой модели
        Метод: info
        """
        logger.info(f"[scoring] Получение информации о модели: {model}")
        
        params = {
            'model': model,
            'key': self.api_key
        }
        
        result = await self._make_request('info', params)
        
        if result:
            return {
                "model": model,
                "name": result.get('name', ''),
                "description": result.get('description', ''),
                "version": result.get('version', ''),
                "created_date": result.get('created_date'),
                "raw_data": result,
                "status": "found"
            }
        
        return {
            "model": model,
            "name": "",
            "description": "",
            "version": "",
            "created_date": None,
            "raw_data": None,
            "status": "not_found"
        }
    
    async def get_financial_coefficients(self, inn: str, okved: Optional[str] = None, 
                                       region: Optional[int] = None) -> Dict:
        """
        Финансовые коэффициенты компании
        Метод: fincoefs
        """
        logger.info(f"[scoring] Получение финансовых коэффициентов для ИНН {inn}")
        
        params = {
            'inn': inn,
            'key': self.api_key
        }
        
        if okved:
            params['okved'] = okved
        if region:
            params['region'] = str(region)
        
        result = await self._make_request('fincoefs', params)
        
        if result:
            return {
                "inn": inn,
                "coefficients": {
                    "КоэфОборЗапасов": result.get('КоэфОборЗапасов'),
                    "ПериодОборЗапасов": result.get('ПериодОборЗапасов'),
                    "КоэфОборДЗ": result.get('КоэфОборДЗ'),
                    "ПериодОборДЗ": result.get('ПериодОборДЗ'),
                    "КоэфОборКЗ": result.get('КоэфОборКЗ'),
                    "ПериодОборКЗ": result.get('ПериодОборКЗ'),
                    "КоэфОборАктивов": result.get('КоэфОборАктивов'),
                    "РентАктивов": result.get('РентАктивов'),
                    "РентСК": result.get('РентСК'),
                    "РентПродаж": result.get('РентПродаж'),
                    "ЧистРентПродаж": result.get('ЧистРентПродаж'),
                    "КоэфТекЛикв": result.get('КоэфТекЛикв'),
                    "КоэфАбсЛикв": result.get('КоэфАбсЛикв'),
                    "КоэфФинАвт": result.get('КоэфФинАвт'),
                    "КоэфФинЗав": result.get('КоэфФинЗав'),
                    "КоэфФинЛевер": result.get('КоэфФинЛевер')
                },
                "comparison": result.get('comparison', {}),
                "raw_data": result,
                "status": "found"
            }
        
        return {
            "inn": inn,
            "coefficients": {},
            "comparison": {},
            "raw_data": None,
            "status": "not_found"
        }
    
    async def get_comprehensive_scoring(self, inn: str) -> Dict:
        """
        Комплексный скоринг по всем доступным моделям
        """
        logger.info(f"[scoring] Комплексный скоринг для ИНН {inn}")
        
        results = {}
        
        # Получаем скоринг по всем доступным моделям
        for model in self.available_models.keys():
            try:
                result = await self.calculate_risk_score(inn, model)
                results[model] = result
            except Exception as e:
                logger.error(f"[scoring] Ошибка при скоринге модели {model}: {e}")
                results[model] = {"status": "error", "error": str(e)}
        
        # Получаем финансовые коэффициенты
        try:
            fin_coefs = await self.get_financial_coefficients(inn)
            results['financial_coefficients'] = fin_coefs
        except Exception as e:
            logger.error(f"[scoring] Ошибка при получении финансовых коэффициентов: {e}")
            results['financial_coefficients'] = {"status": "error", "error": str(e)}
        
        return {
            "inn": inn,
            "results": results,
            "models_checked": len(self.available_models),
            "status": "completed"
        }
    
    def get_available_models(self) -> Dict[str, str]:
        """Возвращает список доступных скоринговых моделей"""
        return self.available_models.copy()
    
    def format_scoring_summary(self, scoring_data: Dict) -> str:
        """Форматирует сводку по скорингу"""
        if not scoring_data or scoring_data.get('status') != 'success':
            return "Скоринг не выполнен"
        
        score = scoring_data.get('score', 0)
        risk_level = scoring_data.get('risk_level', 'unknown')
        probability = scoring_data.get('probability', 0)
        
        summary = f"📊 Скоринг: {score}\n"
        summary += f"🎯 Уровень риска: {risk_level}\n"
        summary += f"📈 Вероятность: {probability:.2f}%\n"
        
        factors = scoring_data.get('factors', [])
        if factors:
            summary += "\n🔍 Факторы риска:\n"
            for factor in factors[:3]:  # Показываем первые 3 фактора
                summary += f"• {factor}\n"
        
        return summary
    
    def format_financial_summary(self, fin_data: Dict) -> str:
        """Форматирует сводку по финансовым коэффициентам"""
        if not fin_data or fin_data.get('status') != 'found':
            return "Финансовые данные не найдены"
        
        coefs = fin_data.get('coefficients', {})
        
        summary = "💰 Финансовые показатели:\n"
        
        # Ключевые коэффициенты
        key_coefs = {
            'КоэфТекЛикв': 'Текущая ликвидность',
            'РентАктивов': 'Рентабельность активов',
            'КоэфФинАвт': 'Финансовая автономия',
            'РентПродаж': 'Рентабельность продаж'
        }
        
        for coef_code, coef_name in key_coefs.items():
            value = coefs.get(coef_code)
            if value is not None:
                summary += f"• {coef_name}: {value:.2f}\n"
        
        return summary

# Создаем глобальный экземпляр
scoring_api = DamiaScoringAPI() 