import requests
from typing import Optional, List, Dict, Any
from config import TENDERGURU_API_CODE

BASE_URL = "https://www.tenderguru.ru/api2.3/export"

class TenderGuruAPI:
    def __init__(self, api_code: str):
        self.api_code = api_code

    def _get(self, endpoint: str, params: dict) -> dict:
        params = params.copy()
        params['dtype'] = 'json'
        params['api_code'] = self.api_code
        url = f"{BASE_URL}{endpoint}"
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if not data or (isinstance(data, dict) and not data):
                return {'results': [], 'error': 'Пустой ответ'}
            return {'results': data}
        except Exception as e:
            return {'results': [], 'error': str(e)}

    def get_tenders_by_keywords(self, kwords: str, fz: int = 44, price_min: Optional[int] = None, price_max: Optional[int] = None, region: Optional[str] = None, page: int = 1) -> dict:
        params = {'kwords': kwords, 'fz': fz, 'page': page}
        if price_min:
            params['price1'] = price_min
        if price_max:
            params['price2'] = price_max
        if region:
            params['region'] = region
        return self._get("/torgi", params)

    def get_contracts_by_keywords(self, kwords: str, page: int = 1) -> List[Dict[str, Any]]:
        params = {'kwords': kwords, 'page': page}
        result = self._get("/contracts", params)
        contracts = []
        for item in result.get('results', []):
            contracts.append({
                'id': item.get('ID'),
                'name': item.get('ContractName'),
                'price': item.get('Price'),
                'date': item.get('Date'),
                'inn': item.get('INN'),
                'supplier': item.get('Org'),
                'region': item.get('Region'),
                'customer': item.get('Customer'),
                'customer_inn': item.get('CustomerINN'),
                'contract_link': item.get('ContractLink'),
            })
        return contracts if contracts else result

    def get_contacts_by_inn(self, inn: str) -> dict:
        url = f"{BASE_URL}/contragent/inn/{inn}/contact"
        params = {'dtype': 'json', 'api_code': self.api_code}
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data if data else {'error': 'Пустой ответ'}
        except Exception as e:
            return {'error': str(e)}

    def get_winners_by_inn(self, inn: str, page: int = 1) -> dict:
        params = {'inn': inn, 'page': page}
        return self._get("/contracts", params)

    def get_planned_procurements(self, kwords: str, page: int = 1) -> dict:
        params = {'kwords': kwords, 'page': page}
        return self._get("/planzakup", params)

    def get_product_stats_by_okpd(self, okpd2: str, page: int = 1) -> dict:
        params = {'kwords': okpd2, 'page': page}
        return self._get("/contracts/products", params)


def main():
    api = TenderGuruAPI(TENDERGURU_API_CODE)
    print("\n--- Поиск тендеров по ключевым словам ---")
    print(api.get_tenders_by_keywords("цемент", price_min=100000))
    print("\n--- Поиск контрактов по ключевым словам ---")
    print(api.get_contracts_by_keywords("бумага"))
    print("\n--- Контакты по ИНН ---")
    print(api.get_contacts_by_inn("7707083893"))
    print("\n--- Победители по ИНН ---")
    print(api.get_winners_by_inn("7707083893"))
    print("\n--- Планы закупок по ключевым словам ---")
    print(api.get_planned_procurements("ремонт"))
    print("\n--- Статистика по продукции (ОКПД2) ---")
    print(api.get_product_stats_by_okpd("19.20.21"))

def get_tender_history_by_inn(inn: str) -> dict:
    """Возвращает историю тендеров по ИНН через TenderGuruAPI."""
    api = TenderGuruAPI(TENDERGURU_API_CODE)
    # Используем get_winners_by_inn как наиболее подходящий метод
    return api.get_winners_by_inn(inn)

def format_tender_history(tender_data: dict) -> str:
    """Форматирует историю тендеров для Telegram."""
    if not tender_data or 'results' not in tender_data or not tender_data['results']:
        return 'Нет данных по истории тендеров.'
    tenders = tender_data['results']
    lines = [f"🏆 История тендеров (победы): {len(tenders)}"]
    for t in tenders[:5]:
        name = t.get('ContractName') or t.get('name') or t.get('contract_link', '—')
        price = t.get('Price') or t.get('price', '—')
        date = t.get('Date') or t.get('date', '—')
        lines.append(f"• {name} | {price} ₽ | {date}")
    if len(tenders) > 5:
        lines.append(f"... и ещё {len(tenders)-5} контрактов")
    return '\n'.join(lines)

if __name__ == "__main__":
    main() 