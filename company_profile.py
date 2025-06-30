from exportbase_api import get_company_by_inn, format_company_info
from tenderguru_api import get_tender_history_by_inn, format_tender_history
from fssp_api import get_fssp_by_inn, format_fssp_info
from arbitr_api import get_arbitr_by_inn, format_arbitr_info


def build_company_profile(inn: str) -> str:
    """
    Агрегирует профиль компании по ИНН: ExportBase, TenderGuru, ФССП, Арбитраж
    Возвращает готовый текст для Telegram.
    """
    blocks = []
    # 1. Основная информация ExportBase
    info = get_company_by_inn(inn)
    blocks.append(format_company_info(info))
    # 2. История тендеров TenderGuru
    tenders = get_tender_history_by_inn(inn)
    blocks.append(format_tender_history(tenders))
    # 3. ФССП
    fssp = get_fssp_by_inn(inn)
    blocks.append(format_fssp_info(fssp or {}))
    # 4. Арбитраж
    arbitr = get_arbitr_by_inn(inn)
    blocks.append(format_arbitr_info(arbitr))
    return '\n\n'.join(blocks) 