from __future__ import annotations

from typing import TYPE_CHECKING

from ..entities.balance import Balance
from ..entities.receipt import Receipt, ReceiptPage

if TYPE_CHECKING:  # pragma: no cover
    from ..ggsel import GGsel


class AccountAPI:
    def __init__(self, client: GGsel) -> None:
        self._client = client

    @property
    def seller_id(self) -> int | None:
        return self._client.seller_id

    async def balance(self) -> Balance:
        response = await self._client._require_raw().account.balance()
        content = response.content
        if content is None:
            return Balance()
        return Balance(
            free=content.amount_t_free,
            locked=content.amount_t_lock,
            plus=content.amount_t_plus,
        )

    async def receipts(
        self,
        *,
        page: int = 1,
        count: int = 100,
        currency: str | None = None,
        operation_type: str | None = None,
        code_filter: str | None = None,
        allow_type: str | None = None,
        start: str | None = None,
        finish: str | None = None,
    ) -> ReceiptPage:
        response = await self._client._require_raw().account.receipts(
            page=page,
            count=count,
            currency=currency,
            operation_type=operation_type,
            code_filter=code_filter,
            allow_type=allow_type,
            start=start,
            finish=finish,
        )
        content = response.content
        if content is None:
            return ReceiptPage(page=page, count=count)
        return ReceiptPage(
            page=content.page,
            count=content.count,
            total_count=content.total_count,
            total_pages=content.total_pages,
            has_next_page=content.has_next_page,
            items=[Receipt.from_schema(item) for item in content.items],
        )
