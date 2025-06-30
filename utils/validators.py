import re
from typing import Optional, Tuple

STOPWORDS = [
    'тендер', 'закупка', 'госзакупка', 'государственный', 'лот', 'номер', 'поиск',
    'пример', 'sample', 'test', 'тест', 'demo', 'демо'
]

PLATFORM_MAPPING = {
    "sberbank-ast.ru": "e1",
    "roseltorg.ru": "e2",
    "zakazrf.ru": "e3",
    "fabrikant.ru": "e12",
    "setonline.ru": "e14",
    "rts-tender.ru": "e16",
    "b2b-center.ru": "e21",
    "tenderguru.ru": "e97",
    "oborontorg.ru": "e22",
    "tender.pro": "e24",
    "com.sberbank-ast.ru": "e26",
    "trade.sberbank-ast.ru": "e28",
    "atom.roseltorg.ru": "e32",
    "etpgpb.ru": "e46",
    "tektorg.ru": "e60",
    "zakupki.rosatom.ru": "e8",
    "etpgaz.gazprom.ru": "e11",
    "zakupki.mts.ru": "e15",
    "zakupki.rosneft.ru": "e17",
    "zakupki.rushydro.ru": "e19",
}

def is_valid_inn(inn: str):
    inn = inn.strip()
    if not re.fullmatch(r"\d{10}|\d{12}", inn):
        return False, "ИНН должен состоять из 10 или 12 цифр."
    if len(inn) == 10:
        # Контрольная сумма для юрлиц
        factors = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        checksum = sum([int(inn[i]) * factors[i] for i in range(9)]) % 11 % 10
        if checksum != int(inn[9]):
            return False, "Некорректная контрольная сумма ИНН (10 знаков)."
    if len(inn) == 12:
        # Контрольные суммы для физлиц
        factors1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0]
        factors2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8, 0]
        n11 = sum([int(inn[i]) * factors1[i] for i in range(10)]) % 11 % 10
        n12 = sum([int(inn[i]) * factors2[i] for i in range(11)]) % 11 % 10
        if n11 != int(inn[10]) or n12 != int(inn[11]):
            return False, "Некорректная контрольная сумма ИНН (12 знаков)."
    return True, ""

def is_valid_tender_number(text: str):
    text = text.strip()
    if re.fullmatch(r"\d{19,20}", text):
        return True, ""
    if re.search(r"zakupki\.gov\.ru.*regNumber=\d{19,20}", text):
        return True, ""
    return False, "Не удалось извлечь номер тендера из ссылки. Отправьте корректный номер или ссылку."

def is_valid_keywords(text: str):
    text = text.strip().lower()
    if len(text) < 2 or text.isdigit():
        return False, "Ключевые слова должны содержать минимум 2 буквы."
    for stop in STOPWORDS:
        if stop in text:
            return False, "Не используйте слова 'тендер', 'закупка' и т.п."
    if not any(c.isalpha() for c in text):
        return False, "Ключевые слова должны содержать буквы."
    return True, ""

def extract_tender_number(text: str) -> str:
    """
    Извлекает номер тендера (19-20 цифр) из строки или ссылки.
    Возвращает номер или пустую строку, если не найден.
    """
    text = text.strip()
    # Прямое совпадение 19-20 цифр
    m = re.search(r"\b(\d{19,20})\b", text)
    if m:
        return m.group(1)
    # Извлечение из ссылки
    m = re.search(r"regNumber=(\d{19,20})", text)
    if m:
        return m.group(1)
    return ""

def extract_tender_number_from_url_or_text(text: str) -> Optional[str]:
    text = text.strip()
    # Прямое совпадение 19-20 цифр
    m = re.search(r"\b(\d{19,20})\b", text)
    if m:
        return m.group(1)
    # zakupki.gov.ru
    m = re.search(r"regNumber=(\d{19,20})", text)
    if m:
        return m.group(1)
    # sberbank-ast.ru
    m = re.search(r"tenderId=(\d{8,20})", text)
    if m:
        return m.group(1)
    m = re.search(r"sberbank-ast.ru/.*?/tender/(\d{8,20})", text)
    if m:
        return m.group(1)
    # rts-tender.ru
    m = re.search(r"rts-tender.ru/.*?/tender/(\d{8,20})", text)
    if m:
        return m.group(1)
    # commercedev.ru
    m = re.search(r"commercedev.ru/.*?/(\d{8,20})", text)
    if m:
        return m.group(1)
    # regiontorg.ru
    m = re.search(r"regiontorg.ru/.*?/(\d{8,20})", text)
    if m:
        return m.group(1)
    # tektorg.ru
    m = re.search(r"tektorg.ru/.*/procedures/(\d+)", text)
    if m:
        return m.group(1)
    # etpgpb.ru
    m = re.search(r"etpgpb.ru/.*/procedure-(\d+)", text)
    if m:
        return m.group(1)
    # fallback: любые 8-20 цифр в ссылке
    m = re.search(r"(\d{8,20})", text)
    if m:
        return m.group(1)
    return None

def extract_tender_number_and_platform(url: str) -> Tuple[Optional[str], Optional[str]]:
    url = url.strip()
    for domain, code in PLATFORM_MAPPING.items():
        if domain in url:
            # Sberbank-AST
            if domain == "sberbank-ast.ru":
                m = re.search(r"PurchaseId=(\d+)", url)
                if m:
                    return m.group(1), code
                m = re.search(r"tenderId=(\d+)", url)
                if m:
                    return m.group(1), code
            # RTS-Tender
            elif domain == "rts-tender.ru":
                m = re.search(r"tender/(\d+)", url)
                if m:
                    return m.group(1), code
            # B2B-Center
            elif domain == "b2b-center.ru":
                m = re.search(r"tender/(\d+)", url)
                if m:
                    return m.group(1), code
            # Fabrikant
            elif domain == "fabrikant.ru":
                m = re.search(r"purchase/view/(\d+)", url)
                if m:
                    return m.group(1), code
            # ТЭК-Торг
            elif domain == "tektorg.ru":
                m = re.search(r"procedures/(\d+)", url)
                if m:
                    return m.group(1), code
            # Росатом, Газпром, МТС, Роснефть, РусГидро — универсально
            else:
                m = re.search(r"(\d{6,20})", url)
                if m:
                    return m.group(1), code
    # zakupki.gov.ru (госзакупки)
    m = re.search(r"regNumber=(\d{19,20})", url)
    if m:
        return m.group(1), None
    m = re.search(r"\b(\d{19,20})\b", url)
    if m:
        return m.group(1), None
    return None, None

def _test_extract_tender_number_from_url_or_text():
    assert extract_tender_number_from_url_or_text('https://zakupki.gov.ru/epz/order/notice/ea44/view/common-info.html?regNumber=0123456789012345678') == '0123456789012345678'
    assert extract_tender_number_from_url_or_text('https://www.sberbank-ast.ru/purchaseList/procedure/public/procedure/view.html?tid=12345678&tenderId=87654321') == '87654321'
    assert extract_tender_number_from_url_or_text('https://www.rts-tender.ru/auction/tender/12345678') == '12345678'
    assert extract_tender_number_from_url_or_text('https://www.tektorg.ru/sale/procedures/8435411') == '8435411'
    assert extract_tender_number_from_url_or_text('0334300062925000038') == '0334300062925000038'
    assert extract_tender_number_from_url_or_text('random text') is None
    print('extract_tender_number_from_url_or_text: OK')

def _test_extract_tender_number_and_platform():
    assert extract_tender_number_and_platform("https://www.sberbank-ast.ru/procedure/PurchaseView.aspx?PurchaseId=123456") == ("123456", "e1")
    assert extract_tender_number_and_platform("https://zakupki.gov.ru/epz/order/notice/printForm/view.html?regNumber=0174500001123002772") == ("0174500001123002772", None)
    assert extract_tender_number_and_platform("https://www.rts-tender.ru/auction/tender/987654") == ("987654", "e2")
    assert extract_tender_number_and_platform("https://www.b2b-center.ru/tender/5555555") == ("5555555", "e7")
    assert extract_tender_number_and_platform("https://www.fabrikant.ru/purchase/view/8888888/") == ("8888888", "e5")
    assert extract_tender_number_and_platform("https://www.tektorg.ru/sale/procedures/8435411") == ("8435411", "e3")
    assert extract_tender_number_and_platform("https://zakupki.rosatom.ru/1234567") == ("1234567", "e8")
    assert extract_tender_number_and_platform("random text") == (None, None)
    print('extract_tender_number_and_platform: OK')

if __name__ == "__main__":
    _test_extract_tender_number_from_url_or_text()
    _test_extract_tender_number_and_platform() 