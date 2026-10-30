from ..transport import GGselTransport
from .account import RawAccountService
from .categories import RawCategoryService
from .chats import RawChatService
from .products import RawProductService
from .reviews import RawReviewService
from .sales import RawSaleService


class RawAPI:
    """Low-level GGsel seller API (V1 token flow)."""

    def __init__(self, transport: GGselTransport):
        self.account = RawAccountService(transport)
        self.categories = RawCategoryService(transport)
        self.chats = RawChatService(transport)
        self.products = RawProductService(transport)
        self.reviews = RawReviewService(transport)
        self.sales = RawSaleService(transport)


__all__ = [
    "RawAPI",
    "RawAccountService",
    "RawCategoryService",
    "RawChatService",
    "RawProductService",
    "RawReviewService",
    "RawSaleService",
]
