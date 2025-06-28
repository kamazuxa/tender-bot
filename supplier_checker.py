"""
Модуль для проверки поставщиков через различные сервисы
Объединяет данные из ФНС, ФССП, Арбитража и Скоринга
"""

import asyncio
import logging
from typing import Dict, Optional
from damia_api import damia_supplier_api

logger = logging.getLogger(__name__)

def calculate_risk_level(fns_data: Dict, fssp_data: Dict, arbitr_data: list, score_data: Dict) -> str:
    """
    Рассчитывает общий уровень риска на основе всех проверок
    """
    risk_score = 0
    
    # ФНС нарушения и проверки
    if fns_data.get("has_violations"):
        risk_score += 30
    risk_score += fns_data.get("violations_count", 0) * 5
    
    # Дополнительные проверки ФНС
    if fns_data.get("mass_director"):
        risk_score += 25
    if fns_data.get("mass_founder"):
        risk_score += 25
    if fns_data.get("liquidation"):
        risk_score += 40
    if fns_data.get("reorganization"):
        risk_score += 15
    if fns_data.get("unreliable_data"):
        risk_score += 35
    
    # Негативные реестры ФНС
    negative_registers = fns_data.get("negative_registers", [])
    risk_score += len(negative_registers) * 20
    
    # ФССП задолженности - более детальная оценка
    if fssp_data.get("has_debts"):
        risk_score += 25
    risk_score += fssp_data.get("debts_count", 0) * 3
    
    # Дополнительная оценка ФССП
    active_cases = fssp_data.get("active_cases", 0)
    if active_cases > 0:
        risk_score += active_cases * 5  # Активные дела - более серьезный риск
    
    total_debt_amount = fssp_data.get("total_debt_amount", 0)
    if total_debt_amount > 1000000:  # Более 1 млн рублей
        risk_score += 20
    elif total_debt_amount > 100000:  # Более 100 тыс рублей
        risk_score += 10
    
    # Арбитражные дела - более детальная оценка
    arbitr_count = len(arbitr_data) if arbitr_data else 0
    risk_score += arbitr_count * 8
    
    # Дополнительная оценка арбитражных дел
    if arbitr_data:
        # Подсчитываем дела где компания была ответчиком
        defendant_cases = 0
        plaintiff_cases = 0
        
        for case in arbitr_data:
            if isinstance(case, dict):
                # Проверяем роль в деле
                role = case.get('role', '').lower()
                if 'ответчик' in role or 'должник' in role:
                    defendant_cases += 1
                elif 'истец' in role or 'кредитор' in role:
                    plaintiff_cases += 1
        
        # Дела где компания была ответчиком - более серьезный риск
        risk_score += defendant_cases * 12
        risk_score += plaintiff_cases * 4
    
    # Скоринговая оценка - более детальная оценка
    if score_data.get("score") is not None:
        score_value = score_data.get("score", 0)
        if score_value < 400:
            risk_score += 30  # Критический риск
        elif score_value < 600:
            risk_score += 20  # Высокий риск
        elif score_value < 800:
            risk_score += 10  # Средний риск
        # Низкий риск (800+) не добавляет баллов
    else:
        risk_score += 5  # Неизвестный скоринг - небольшой риск
    
    # Определяем уровень риска
    if risk_score >= 80:
        return "🔴 Высокий риск"
    elif risk_score >= 50:
        return "⚠️ Средний риск"
    elif risk_score >= 20:
        return "🟡 Низкий риск"
    else:
        return " Минимальный риск"

async def check_supplier(inn: str) -> Dict:
    """
    Проверяет поставщика по всем сервисам и возвращает агрегированный результат
    
    Args:
        inn: ИНН поставщика
        
    Returns:
        Словарь с результатами проверки
    """
    logger.info(f"[checker] Начинаем проверку поставщика с ИНН: {inn}")
    
    try:
        # Получаем данные из всех источников
        fns_data = await damia_supplier_api.get_fns(inn)
        fssp_data = await damia_supplier_api.get_fssp(inn)
        arbitr_data = await damia_supplier_api.get_arbitr(inn)
        score_data = await damia_supplier_api.get_scoring(inn)
        
        # Обрабатываем исключения
        if isinstance(fns_data, Exception):
            logger.error(f"[checker] Ошибка ФНС для ИНН {inn}: {fns_data}")
            fns_data = {"has_violations": False, "violations_count": 0, "status": "error"}
        
        if isinstance(fssp_data, Exception):
            logger.error(f"[checker] Ошибка ФССП для ИНН {inn}: {fssp_data}")
            fssp_data = {"has_debts": False, "debts_count": 0, "status": "error"}
        
        if isinstance(arbitr_data, Exception):
            logger.error(f"[checker] Ошибка Арбитража для ИНН {inn}: {arbitr_data}")
            arbitr_data = []
        
        if isinstance(score_data, Exception):
            logger.error(f"[checker] Ошибка Скоринга для ИНН {inn}: {score_data}")
            score_data = {"score": 0, "risk_level": "error"}
        
        # Рассчитываем общий риск
        risk_level = calculate_risk_level(fns_data, fssp_data, arbitr_data, score_data)
        
        # Формируем результат
        result = {
            "inn": inn,
            "risk": risk_level,
            "fns": fns_data,
            "fssp": fssp_data,
            "arbitr_count": len(arbitr_data) if arbitr_data else 0,
            "arbitr_cases": arbitr_data[:5] if arbitr_data else [],  # Первые 5 дел
            "score": score_data.get("score", 0),
            "score_level": score_data.get("risk_level", "unknown"),
            "check_date": None,  # TODO: добавить дату проверки
            "summary": {
                "violations": fns_data.get("violations_count", 0),
                "debts": fssp_data.get("debts_count", 0),
                "arbitrage": len(arbitr_data) if arbitr_data else 0,
                "reliability_score": score_data.get("score", 0)
            }
        }
        
        logger.info(f"[checker] Проверка завершена для ИНН {inn}: {risk_level}")
        return result
        
    except Exception as e:
        logger.error(f"[checker] Критическая ошибка при проверке ИНН {inn}: {e}")
        return {
            "inn": inn,
            "risk": "❌ Ошибка проверки",
            "fns": {"status": "error"},
            "fssp": {"status": "error"},
            "arbitr_count": 0,
            "arbitr_cases": [],
            "score": 0,
            "score_level": "error",
            "check_date": None,
            "summary": {
                "violations": 0,
                "debts": 0,
                "arbitrage": 0,
                "reliability_score": 0
            }
        }

def format_supplier_check_result(check_data: Dict) -> str:
    """
    Форматирует результат проверки поставщика для отображения
    """
    if not check_data or check_data.get("risk") == "❌ Ошибка проверки":
        return "❌ Ошибка проверки"
    
    summary = check_data.get("summary", {})
    
    # Формируем краткую информацию
    parts = [
        f"🔍 {check_data.get('risk', 'Неизвестно')}",
        f"🧷 Арбитражи: {summary.get('arbitrage', 0)}",
        f"💰 ФССП: {summary.get('debts', 0)}",
        f"📊 Скоринг: {summary.get('reliability_score', 0)}"
    ]
    
    return " | ".join(parts)

def get_detailed_check_info(check_data: Dict) -> str:
    """
    Возвращает подробную информацию о проверке
    """
    if not check_data or check_data.get("risk") == "❌ Ошибка проверки":
        return "❌ Не удалось получить данные проверки"
    
    fns = check_data.get("fns", {})
    fssp = check_data.get("fssp", {})
    summary = check_data.get("summary", {})
    arbitr_cases = check_data.get("arbitr_cases", [])
    
    details = [
        f"🔍 **Общий риск:** {check_data.get('risk', 'Неизвестно')}",
        f"",
        f"📊 **ФНС:**",
        f"• Нарушения: {summary.get('violations', 0)}",
        f"• Статус: {fns.get('status', 'Неизвестно')}",
    ]
    
    # Дополнительные проверки ФНС
    if fns.get("mass_director"):
        details.append("• ⚠️ Массовый директор")
    if fns.get("mass_founder"):
        details.append("• ⚠️ Массовый учредитель")
    if fns.get("liquidation"):
        details.append("• 🔴 Ликвидация")
    if fns.get("reorganization"):
        details.append("• 🟡 Реорганизация")
    if fns.get("unreliable_data"):
        details.append("• 🔴 Недостоверные данные")
    
    # Негативные реестры
    negative_registers = fns.get("negative_registers", [])
    if negative_registers:
        details.append(f"• 🔴 Негативные реестры: {len(negative_registers)}")
    
    details.extend([
        f"",
        f"📊 **Скоринг:**",
        f"• Модель: {check_data.get('score_data', {}).get('model', 'Неизвестно')}",
        f"• Оценка: {check_data.get('score', 0)}",
        f"• Уровень риска: {check_data.get('score_level', 'Неизвестно')}",
        f"",
        f"💰 **ФССП:**",
        f"• Всего производств: {summary.get('debts', 0)}",
        f"• Активных: {fssp.get('active_cases', 0)}",
        f"• Сумма задолженности: {fssp.get('total_debt_amount', 0):,.0f} ₽" if fssp.get('total_debt_amount') else "• Сумма: Не указана",
        f"",
        f"⚖️ **Арбитраж:**",
        f"• Всего дел: {summary.get('arbitrage', 0)}",
    ])
    
    # Детальная информация об арбитражных делах
    if arbitr_cases:
        defendant_cases = 0
        plaintiff_cases = 0
        
        for case in arbitr_cases[:5]:  # Показываем первые 5 дел
            if isinstance(case, dict):
                role = case.get('role', '').lower()
                if 'ответчик' in role or 'должник' in role:
                    defendant_cases += 1
                elif 'истец' in role or 'кредитор' in role:
                    plaintiff_cases += 1
        
        if defendant_cases > 0:
            details.append(f"• 🔴 Ответчик: {defendant_cases} дел")
        if plaintiff_cases > 0:
            details.append(f"• 🟡 Истец: {plaintiff_cases} дел")
    
    return "\n".join(details) 