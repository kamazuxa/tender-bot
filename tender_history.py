#!/usr/bin/env python3
"""
Модуль анализа истории похожих тендеров
"""

import asyncio
import logging
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from dataclasses import dataclass
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from io import BytesIO
import openai
from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

@dataclass
class TenderPosition:
    """Позиция тендера"""
    name: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    price_per_unit: Optional[float] = None
    total_price: Optional[float] = None

@dataclass
class HistoricalTender:
    """Исторический тендер"""
    tender_id: str
    name: str
    region: str
    publication_date: datetime
    nmck: float
    final_price: Optional[float]
    winner_name: Optional[str]
    winner_inn: Optional[str]
    participants_count: Optional[int]
    subject: str
    status: str  # 'completed', 'failed', 'cancelled'
    price_reduction_percent: Optional[float] = None

class TenderHistoryAnalyzer:
    """Анализатор истории похожих тендеров"""
    
    def __init__(self, damia_client, openai_client=None):
        self.damia_client = damia_client
        self.openai_client = openai_client
        self.cache = {}
        
    async def extract_tender_positions(self, tender_data: Dict) -> List[TenderPosition]:
        """Извлекает позиции из данных тендера"""
        positions = []
        
        try:
            # Извлекаем позиции из разных возможных мест в структуре данных
            products = tender_data.get('Позиции', [])
            if not products:
                products = tender_data.get('products', [])
            if not products:
                products = tender_data.get('items', [])
            
            for product in products:
                if isinstance(product, dict):
                    name = product.get('Название', product.get('name', ''))
                    quantity = product.get('Количество', product.get('quantity'))
                    unit = product.get('Единица', product.get('unit'))
                    price = product.get('Цена', product.get('price'))
                    
                    if name:
                        position = TenderPosition(
                            name=name,
                            quantity=quantity,
                            unit=unit,
                            price_per_unit=price
                        )
                        positions.append(position)
            
            # Если позиции не найдены, создаем общую позицию из названия тендера
            if not positions:
                subject = tender_data.get('Предмет', tender_data.get('subject', ''))
                if subject:
                    positions.append(TenderPosition(name=subject))
                    
        except Exception as e:
            logger.error(f"Ошибка извлечения позиций: {e}")
            
        return positions
    
    async def generate_search_queries(self, positions: List[TenderPosition]) -> List[str]:
        """Генерирует поисковые запросы для поиска похожих тендеров"""
        queries = []
        
        for position in positions:
            # Очищаем название от лишних символов
            clean_name = re.sub(r'[^\w\s]', ' ', position.name)
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
            
            # Разбиваем на ключевые слова
            words = clean_name.split()
            
            # Создаем различные варианты запросов
            if len(words) >= 2:
                # Основной запрос
                queries.append(clean_name)
                
                # Запрос без количества
                if any(word.isdigit() for word in words):
                    text_only = ' '.join([w for w in words if not w.isdigit()])
                    if text_only:
                        queries.append(text_only)
                
                # Запрос по основным словам (первые 2-3 слова)
                main_words = ' '.join(words[:3])
                queries.append(main_words)
            
            # Добавляем единицу измерения если есть
            if position.unit:
                queries.append(f"{clean_name} {position.unit}")
        
        # Убираем дубликаты и пустые запросы
        queries = list(set([q for q in queries if q and len(q) > 2]))
        
        logger.info(f"Сгенерированы запросы: {queries}")
        return queries
    
    async def search_similar_tenders(self, queries: List[str], region: str = None, 
                                   max_price: float = None, min_price: float = None) -> List[Dict]:
        """Ищет похожие тендеры через DaMIA API"""
        similar_tenders = []
        
        # Ограничиваем период поиска последними 12 месяцами
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        
        for query in queries[:5]:  # Ограничиваем количество запросов
            try:
                logger.info(f"Поиск тендеров по запросу: {query}")
                
                # Используем DaMIA API для поиска тендеров
                search_params = {
                    'query': query,
                    'date_from': start_date.strftime('%Y-%m-%d'),
                    'date_to': end_date.strftime('%Y-%m-%d'),
                    'limit': 50
                }
                
                if region:
                    search_params['region'] = region
                
                # Выполняем поиск через DaMIA
                search_results = await self.damia_client.search_tenders(search_params)
                
                if search_results:
                    for tender in search_results:
                        # Фильтруем по цене если указана
                        tender_price = tender.get('НМЦК', tender.get('nmck', 0))
                        if tender_price:
                            if max_price and tender_price > max_price * 1.3:
                                continue
                            if min_price and tender_price < min_price * 0.7:
                                continue
                        
                        similar_tenders.append(tender)
                
                # Небольшая задержка между запросами
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Ошибка поиска по запросу '{query}': {e}")
        
        # Убираем дубликаты по ID тендера
        unique_tenders = {}
        for tender in similar_tenders:
            tender_id = tender.get('РегНомер', tender.get('id'))
            if tender_id and tender_id not in unique_tenders:
                unique_tenders[tender_id] = tender
        
        logger.info(f"Найдено {len(unique_tenders)} уникальных похожих тендеров")
        return list(unique_tenders.values())
    
    async def extract_tender_details(self, tender_data: Dict) -> HistoricalTender:
        """Извлекает детали тендера для анализа"""
        try:
            tender_id = tender_data.get('РегНомер', tender_data.get('id', ''))
            name = tender_data.get('Наименование', tender_data.get('name', ''))
            region = tender_data.get('Регион', tender_data.get('region', ''))
            
            # Парсим дату
            date_str = tender_data.get('ДатаПубл', tender_data.get('publication_date', ''))
            publication_date = datetime.now()
            if date_str:
                try:
                    publication_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except:
                    pass
            
            # Извлекаем цены
            nmck = tender_data.get('НМЦК', tender_data.get('nmck', 0))
            final_price = tender_data.get('ЦенаКонтракта', tender_data.get('final_price'))
            
            # Извлекаем информацию о победителе
            winner_info = tender_data.get('Победитель', tender_data.get('winner', {}))
            winner_name = None
            winner_inn = None
            if isinstance(winner_info, dict):
                winner_name = winner_info.get('Наименование', winner_info.get('name'))
                winner_inn = winner_info.get('ИНН', winner_info.get('inn'))
            elif isinstance(winner_info, str):
                winner_name = winner_info
            
            # Количество участников
            participants_count = tender_data.get('КолУчастников', tender_data.get('participants_count'))
            
            # Статус тендера
            status = tender_data.get('Статус', tender_data.get('status', 'unknown'))
            if 'заверш' in status.lower() or 'выполн' in status.lower():
                status = 'completed'
            elif 'отмен' in status.lower() or 'отказ' in status.lower():
                status = 'cancelled'
            elif 'не состоял' in status.lower() or 'не было' in status.lower():
                status = 'failed'
            
            # Рассчитываем снижение цены
            price_reduction_percent = None
            if nmck and final_price and nmck > 0:
                price_reduction_percent = ((nmck - final_price) / nmck) * 100
            
            return HistoricalTender(
                tender_id=tender_id,
                name=name,
                region=region,
                publication_date=publication_date,
                nmck=nmck,
                final_price=final_price,
                winner_name=winner_name,
                winner_inn=winner_inn,
                participants_count=participants_count,
                subject=name,
                status=status,
                price_reduction_percent=price_reduction_percent
            )
            
        except Exception as e:
            logger.error(f"Ошибка извлечения деталей тендера: {e}")
            return None
    
    async def analyze_price_dynamics(self, historical_tenders: List[HistoricalTender], 
                                   current_price: float) -> Dict:
        """Анализирует динамику цен"""
        if not historical_tenders:
            return {}
        
        # Фильтруем только завершенные тендеры с ценами
        completed_tenders = [
            t for t in historical_tenders 
            if t.status == 'completed' and t.final_price and t.final_price > 0
        ]
        
        if not completed_tenders:
            return {}
        
        # Сортируем по дате
        completed_tenders.sort(key=lambda x: x.publication_date)
        
        # Рассчитываем статистику
        prices = [t.final_price for t in completed_tenders]
        avg_price = np.mean(prices)
        median_price = np.median(prices)
        min_price = min(prices)
        max_price = max(prices)
        
        # Сравнение с текущей ценой
        price_comparison = {}
        if current_price > 0:
            price_comparison = {
                'current_vs_avg': ((current_price - avg_price) / avg_price) * 100 if avg_price > 0 else 0,
                'current_vs_median': ((current_price - median_price) / median_price) * 100 if median_price > 0 else 0,
                'current_vs_min': ((current_price - min_price) / min_price) * 100 if min_price > 0 else 0,
                'current_vs_max': ((current_price - max_price) / max_price) * 100 if max_price > 0 else 0
            }
        
        return {
            'total_tenders': len(completed_tenders),
            'avg_price': avg_price,
            'median_price': median_price,
            'min_price': min_price,
            'max_price': max_price,
            'price_comparison': price_comparison,
            'tenders': completed_tenders
        }
    
    async def generate_price_chart(self, historical_tenders: List[HistoricalTender], 
                                 current_price: float, current_date: datetime) -> BytesIO:
        """Генерирует график динамики цен"""
        # Фильтруем завершенные тендеры
        completed_tenders = [
            t for t in historical_tenders 
            if t.status == 'completed' and t.final_price and t.final_price > 0
        ]
        
        if not completed_tenders:
            return None
        
        # Создаем график
        plt.figure(figsize=(12, 8))
        
        # Данные для графика
        dates = [t.publication_date for t in completed_tenders]
        prices = [t.final_price for t in completed_tenders]
        
        # График исторических цен
        plt.scatter(dates, prices, alpha=0.7, s=100, label='Исторические тендеры')
        
        # Линия тренда
        if len(dates) > 1:
            z = np.polyfit(mdates.date2num(dates), prices, 1)
            p = np.poly1d(z)
            plt.plot(dates, p(mdates.date2num(dates)), "r--", alpha=0.8, label='Тренд')
        
        # Текущая цена
        plt.axhline(y=current_price, color='g', linestyle='-', linewidth=2, label=f'Текущий тендер ({current_price:,.0f} ₽)')
        
        # Средняя цена
        avg_price = np.mean(prices)
        plt.axhline(y=avg_price, color='orange', linestyle='--', alpha=0.7, label=f'Средняя цена ({avg_price:,.0f} ₽)')
        
        # Настройка графика
        plt.title('Динамика цен по похожим тендерам', fontsize=16, fontweight='bold')
        plt.xlabel('Дата публикации', fontsize=12)
        plt.ylabel('Цена контракта (₽)', fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Форматирование дат
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m.%Y'))
        plt.gca().xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.xticks(rotation=45)
        
        # Сохраняем в буфер
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        plt.close()
        
        return buffer
    
    async def generate_analysis_report(self, historical_tenders: List[HistoricalTender], 
                                     current_tender: Dict, price_analysis: Dict) -> str:
        """Генерирует текстовый отчет анализа"""
        if not historical_tenders:
            return "📊 **История похожих тендеров не найдена**\n\nПохожие тендеры за последние 12 месяцев не обнаружены."
        
        # Сортируем по дате (новые сначала)
        historical_tenders.sort(key=lambda x: x.publication_date, reverse=True)
        
        # Текущий тендер
        current_price = current_tender.get('НМЦК', current_tender.get('nmck', 0))
        current_subject = current_tender.get('Предмет', current_tender.get('subject', ''))
        
        report = f"📈 **История похожих тендеров**\n\n"
        report += f"🔍 **Анализируемый тендер:**\n"
        report += f"📋 {current_subject}\n"
        report += f"💰 НМЦК: {current_price:,.0f} ₽\n\n"
        
        # Исторические тендеры
        report += "📊 **Похожие тендеры за последние 12 месяцев:**\n\n"
        
        for i, tender in enumerate(historical_tenders[:10], 1):  # Показываем первые 10
            date_str = tender.publication_date.strftime('%d.%m.%Y')
            
            if tender.status == 'completed' and tender.winner_name:
                status_icon = "✅"
                winner_info = f"Победа при {tender.participants_count} участниках" if tender.participants_count else "Победа"
                price_info = f"💰 Цена: {tender.final_price:,.0f} ₽"
                
                if tender.price_reduction_percent:
                    price_info += f" ({tender.price_reduction_percent:+.1f}% от НМЦК)"
            else:
                status_icon = "❌"
                winner_info = "Провален (не было заявок)" if tender.status == 'failed' else "Отменен"
                price_info = f"💰 НМЦК: {tender.nmck:,.0f} ₽"
            
            report += f"{i}️⃣ {date_str} — {tender.winner_name or 'Неизвестно'}\n"
            report += f"   {status_icon} {winner_info}\n"
            report += f"   {price_info}\n"
            if tender.region:
                report += f"   📍 Регион: {tender.region}\n"
            report += "\n"
        
        # Анализ цен
        if price_analysis:
            report += "📉 **Анализ цен:**\n"
            report += f"• Средняя цена: {price_analysis['avg_price']:,.0f} ₽\n"
            report += f"• Медианная цена: {price_analysis['median_price']:,.0f} ₽\n"
            report += f"• Диапазон: {price_analysis['min_price']:,.0f} - {price_analysis['max_price']:,.0f} ₽\n\n"
            
            comparison = price_analysis.get('price_comparison', {})
            if comparison:
                report += f"📊 **Сравнение с текущим тендером:**\n"
                report += f"• От средней: {comparison['current_vs_avg']:+.1f}%\n"
                report += f"• От медианной: {comparison['current_vs_median']:+.1f}%\n"
                report += f"• От минимальной: {comparison['current_vs_min']:+.1f}%\n"
                report += f"• От максимальной: {comparison['current_vs_max']:+.1f}%\n\n"
        
        # Выводы
        report += "📌 **Выводы:**\n"
        if price_analysis and price_analysis.get('price_comparison'):
            comparison = price_analysis['price_comparison']
            if comparison['current_vs_avg'] > 20:
                report += "⚠️ Цена значительно выше средней. Возможно, есть риск отклонения заявки из-за завышения.\n"
            elif comparison['current_vs_avg'] > 10:
                report += "⚠️ Цена выше средней. Рекомендуется проанализировать обоснованность цены.\n"
            elif comparison['current_vs_avg'] < -20:
                report += "✅ Цена значительно ниже средней. Возможно, есть риск отклонения заявки из-за занижения.\n"
            elif comparison['current_vs_avg'] < -10:
                report += "✅ Цена ниже средней. Хорошие шансы на победу.\n"
            else:
                report += "✅ Цена в пределах среднего диапазона. Конкурентная цена.\n"
        else:
            report += "📊 Недостаточно данных для анализа цен.\n"
        
        return report
    
    async def analyze_tender_history(self, tender_data: Dict) -> Dict:
        """Основной метод анализа истории похожих тендеров"""
        try:
            logger.info("Начинаем анализ истории похожих тендеров")
            
            # Извлекаем позиции тендера
            positions = await self.extract_tender_positions(tender_data)
            if not positions:
                logger.warning("Не удалось извлечь позиции тендера")
                return {'error': 'Не удалось извлечь позиции тендера'}
            
            # Генерируем поисковые запросы
            queries = await self.generate_search_queries(positions)
            if not queries:
                logger.warning("Не удалось сгенерировать поисковые запросы")
                return {'error': 'Не удалось сгенерировать поисковые запросы'}
            
            # Ищем похожие тендеры
            current_price = tender_data.get('НМЦК', tender_data.get('nmck', 0))
            region = tender_data.get('Регион', tender_data.get('region'))
            
            similar_tenders = await self.search_similar_tenders(
                queries, 
                region=region,
                max_price=current_price * 1.3 if current_price else None,
                min_price=current_price * 0.7 if current_price else None
            )
            
            if not similar_tenders:
                logger.info("Похожие тендеры не найдены")
                return {'error': 'Похожие тендеры не найдены за последние 12 месяцев'}
            
            # Извлекаем детали тендеров
            historical_tenders = []
            for tender in similar_tenders:
                details = await self.extract_tender_details(tender)
                if details:
                    historical_tenders.append(details)
            
            # Анализируем динамику цен
            price_analysis = await self.analyze_price_dynamics(historical_tenders, current_price)
            
            # Генерируем отчет
            report = await self.generate_analysis_report(historical_tenders, tender_data, price_analysis)
            
            # Генерируем график
            chart_buffer = None
            if historical_tenders and current_price:
                chart_buffer = await self.generate_price_chart(historical_tenders, current_price, datetime.now())
            
            return {
                'success': True,
                'report': report,
                'chart': chart_buffer,
                'historical_tenders': historical_tenders,
                'price_analysis': price_analysis,
                'total_found': len(historical_tenders)
            }
            
        except Exception as e:
            logger.error(f"Ошибка анализа истории тендеров: {e}")
            return {'error': f'Ошибка анализа: {str(e)}'} 