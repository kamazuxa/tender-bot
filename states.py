from enum import Enum, auto

class BotState(Enum):
    MAIN_MENU = auto()
    ANALYZE = auto()
    SEARCH = auto()
    SUPPLIER = auto()
    ANALYTICS = auto()
    PROFILE = auto()
    HELP = auto()
    LOCKED = auto()
    # Вложенные состояния для пошаговых сценариев
    WAIT_TENDER_NUMBER = auto()
    WAIT_KEYWORDS = auto()
    WAIT_INN = auto()
    WAIT_CONTACT_ACTION = auto()
    WAIT_ANALYTICS_ACTION = auto()
    WAIT_PROFILE_ACTION = auto()
    WAIT_EMAIL_ACTION = auto()
    # ... можно добавить другие по мере необходимости ... 