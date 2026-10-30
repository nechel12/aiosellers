from enum import Enum, StrEnum


class EventTypes(Enum):
    INITIAL_CHAT = 0
    NEW_MESSAGE = 1
    NEW_SALE = 2
    NEW_REVIEW = 3


class MessageDirection(StrEnum):
    BUYER = "buyer"
    SELLER = "seller"
    SYSTEM = "system"


class PriceModifyType(StrEnum):
    PERCENT_PLUS = "percentplus"
    PERCENT_MINUS = "percentminus"
    PRICE_MINUS = "priceminus"
    PRICE_PLUS = "priceplus"


class Currency(StrEnum):
    USD = "USD"
    EUR = "EUR"
    RUB = "RUB"


INVOICE_STATE_NAMES: dict[int, str] = {
    1: "created",
    2: "cancelled",
    3: "paid",
    4: "completed",
    5: "refunded",
}
