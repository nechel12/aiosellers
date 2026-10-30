from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..schemas import INVOICE_STATE_NAMES, SaleSchema

if TYPE_CHECKING:  # pragma: no cover
    from ..ggsel import GGsel


@dataclass(slots=True)
class Purchase:
    invoice_id: int | None = None
    item_id: int | None = None
    cart_uid: str | None = None
    name: str | None = None
    amount: float | None = None
    currency: str | None = None
    state: int | None = None
    purchase_date: datetime | None = None
    paid_at: datetime | None = None
    buyer_email: str | None = None
    profit: float | None = None
    options: list[dict[str, Any]] = field(default_factory=list)
    feedback: dict[str, Any] | None = None
    unique_code_state: Any | None = None

    _client: GGsel | None = field(default=None, repr=False, init=False, compare=False)

    @property
    def state_name(self) -> str | None:
        return INVOICE_STATE_NAMES.get(self.state) if self.state is not None else None


@dataclass(slots=True)
class Sale:
    invoice_id: int
    date: datetime | None = None
    product_id: int | None = None
    product_name: str | None = None
    price_rub: float | None = None
    price_usd: float | None = None
    price_eur: float | None = None
    price_uah: float | None = None

    _client: GGsel | None = field(default=None, repr=False, init=False, compare=False)

    @classmethod
    def from_schema(cls, schema: SaleSchema) -> Sale:
        product = schema.product
        return cls(
            invoice_id=schema.invoice_id,
            date=schema.date,
            product_id=product.id if product is not None else None,
            product_name=product.name if product is not None else None,
            price_rub=product.price_rub if product is not None else None,
            price_usd=product.price_usd if product is not None else None,
            price_eur=product.price_eur if product is not None else None,
            price_uah=product.price_uah if product is not None else None,
        )

    def _require_client(self) -> GGsel:
        if self._client is None:
            raise RuntimeError(
                f"{self.__class__.__name__} is not attached to a client. "
                f"Use client.sales.last() to fetch an active instance."
            )
        return self._client

    async def purchase(self) -> Purchase:
        return await self._require_client().sales.get(self.invoice_id)

    async def get_product(self):
        if not self.product_id:
            return None
        return await self._require_client().products.get(self.product_id)
