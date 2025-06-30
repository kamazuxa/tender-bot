import requests

EXPORTBASE_API_URL = "https://export-base.ru/api/"
EXPORTBASE_API_KEY = "ВАШ_API_КЛЮЧ"  # TODO: заменить на реальный ключ или импортировать из config

def get_company_by_inn(inn: str) -> dict:
    """Получить данные о компании по ИНН через ExportBase API"""
    params = {
        "inn": inn,
        "key": EXPORTBASE_API_KEY
    }
    response = requests.get(EXPORTBASE_API_URL + "company/", params=params)
    response.raise_for_status()
    data = response.json()
    # companies_data — массив компаний, берём первую
    companies = data.get("companies_data", [])
    return companies[0] if companies else {}

def get_full_company_profile_by_inn(inn: str) -> dict:
    """Получить полный профиль компании по ИНН (все поля) через ExportBase API"""
    params = {
        "inn": inn,
        "key": EXPORTBASE_API_KEY
    }
    response = requests.get(EXPORTBASE_API_URL + "company/", params=params)
    response.raise_for_status()
    data = response.json()
    companies = data.get("companies_data", [])
    return companies[0] if companies else {}

def format_company_info(company: dict) -> str:
    """Форматировать данные компании для Telegram"""
    return (
        f"🏢 <b>{company.get('legal_name', 'Не указано')}</b>\n"
        f"ИНН: <code>{company.get('inn', '—')}</code>\n"
        f"ОГРН: <code>{company.get('ogrn', '—')}</code>\n"
        f"ОКВЭД: {company.get('main_okved_code', '—')} {company.get('main_okved_name', '')}\n"
        f"Адрес: {company.get('address', '—')}\n"
        f"Телефон: {company.get('stationary_phone', '—')} / {company.get('mobile_phone', '—')}\n"
        f"Email: {company.get('email', '—')}\n"
        f"Сайт: {company.get('site', '—')}\n"
        f"Руководитель: {company.get('ceo_name', '—')} ({company.get('ceo_position', '—')})\n"
        f"Дата регистрации: {company.get('reg_date', '—')}\n"
        f"Сотрудников: {company.get('employees', '—')}\n"
        f"Выручка: {company.get('income', '—')} тыс. руб.\n"
        f"Статус: {'Действующая' if company.get('active', 1) == 1 else 'Закрыта'}"
    )

def format_full_company_profile(company: dict) -> str:
    """Форматировать полный профиль компании для Telegram (все основные поля)"""
    if not company:
        return "❌ Данные компании не найдены."
    fields = [
        ("Наименование", company.get("legal_name", "—")),
        ("ИНН", company.get("inn", "—")),
        ("ОГРН", company.get("ogrn", "—")),
        ("КПП", company.get("kpp", "—")),
        ("Адрес", company.get("address", "—")),
        ("Регион", company.get("region", "—")),
        ("Населённый пункт", company.get("locality", "—")),
        ("ОКВЭД", f"{company.get('main_okved_code', '—')} {company.get('main_okved_name', '')}"),
        ("Дата регистрации", company.get("reg_date", "—")),
        ("Сотрудников", company.get("employees", "—")),
        ("Выручка", f"{company.get('income', '—')} тыс. руб."),
        ("Телефон", company.get("stationary_phone", "—")),
        ("Мобильный", company.get("mobile_phone", "—")),
        ("Email", company.get("email", "—")),
        ("Сайт", company.get("site", "—")),
        ("Руководитель", f"{company.get('ceo_name', '—')} ({company.get('ceo_position', '—')})"),
        ("Статус", "Действующая" if company.get("active", 1) == 1 else "Закрыта")
    ]
    result = "<b>Полный профиль компании</b>\n"
    for name, value in fields:
        result += f"<b>{name}:</b> {value}\n"
    return result.strip() 