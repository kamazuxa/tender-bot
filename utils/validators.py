import re

STOPWORDS = [
    'тендер', 'закупка', 'госзакупка', 'государственный', 'лот', 'номер', 'поиск',
    'пример', 'sample', 'test', 'тест', 'demo', 'демо'
]

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