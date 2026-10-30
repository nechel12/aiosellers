from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from ..schemas import ReviewSchema

if TYPE_CHECKING:  # pragma: no cover
    from ..ggsel import GGsel
    from .product import Product


@dataclass(slots=True)
class Review:
    id: int
    text: str | None = None
    product_id: int | None = None
    type: str | None = None
    date: datetime | None = None
    invoice_id: int | None = None
    product_name: str | None = None
    comment: str | None = None
    owner_id: int | None = None

    _client: GGsel | None = field(default=None, repr=False, init=False, compare=False)

    @classmethod
    def from_schema(cls, schema: ReviewSchema) -> Review:
        return cls(
            id=schema.id,
            text=schema.info,
            product_id=schema.good,
            type=schema.type,
            date=schema.date,
            invoice_id=schema.invoice_id,
            product_name=schema.name,
            comment=schema.comment,
            owner_id=schema.owner_id,
        )

    def _require_client(self) -> GGsel:
        if self._client is None:
            raise RuntimeError(
                f"{self.__class__.__name__} is not attached to a client. "
                f"Use client.reviews.list() to fetch an active instance."
            )
        return self._client

    async def get_product(self) -> Product | None:
        if not self.product_id:
            return None
        return await self._require_client().products.get(self.product_id)

    async def get_purchase(self):
        if not self.invoice_id:
            return None
        return await self._require_client().sales.get(self.invoice_id)
