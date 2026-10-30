from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.exceptions import RequestFailedError
from ..entities.sale import Purchase, Sale
from ..schemas import PurchaseContent, UniqueCodeResponse

if TYPE_CHECKING:  # pragma: no cover
    from ..ggsel import GGsel


class SaleAPI:
    def __init__(self, client: GGsel) -> None:
        self._client = client

    def _to_sale(self, schema) -> Sale:
        sale = Sale.from_schema(schema)
        sale._client = self._client
        return sale

    @staticmethod
    def _purchase(content: PurchaseContent) -> Purchase:
        buyer = content.buyer_info
        return Purchase(
            invoice_id=content.content_id,
            item_id=content.item_id,
            cart_uid=content.cart_uid,
            name=content.name,
            amount=content.amount,
            currency=content.currency_type,
            state=content.invoice_state,
            purchase_date=content.purchase_date,
            paid_at=content.date_pay,
            buyer_email=buyer.email if buyer is not None else None,
            profit=content.profit,
            options=[option.model_dump() for option in content.options],
            feedback=content.feedback.model_dump() if content.feedback is not None else None,
            unique_code_state=content.unique_code_state,
        )

    @staticmethod
    def _purchase_by_code(response: UniqueCodeResponse) -> Purchase:
        return Purchase(
            invoice_id=response.inv,
            item_id=response.id_goods,
            cart_uid=response.cart_uid,
            name=response.name_invoice,
            amount=response.amount,
            currency=response.type_curr,
            paid_at=response.date_pay,
            buyer_email=response.email,
            profit=response.profit,
            options=[option.model_dump() for option in response.options],
            unique_code_state=response.unique_code_state,
        )

    async def last(
        self,
        *,
        top: int = 10,
        group: bool | None = None,
    ) -> list[Sale]:
        response = await self._client._require_raw().sales.last_sales(
            top=min(100, max(1, top)),
            group=group,
            seller_id=self._client.seller_id,
        )
        return [self._to_sale(schema) for schema in response.sales]

    async def get(self, invoice_id: int | str) -> Purchase:
        response = await self._client._require_raw().sales.purchase(invoice_id)
        if response.content is None:
            raise RequestFailedError(f"GGsel purchase {invoice_id} was not found")
        purchase = self._purchase(response.content)
        purchase._client = self._client
        return purchase

    async def get_by_unique_code(self, unique_code: str) -> Purchase:
        response = await self._client._require_raw().sales.purchase_by_unique_code(unique_code)
        purchase = self._purchase_by_code(response)
        purchase._client = self._client
        return purchase
