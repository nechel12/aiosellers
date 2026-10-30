from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from ..schemas import ProductData, ProductRow, SaleInfo

if TYPE_CHECKING:  # pragma: no cover
    from ..ggsel import GGsel


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sale_price(info: SaleInfo | None, currency: str | None) -> float | None:
    if info is None:
        return None
    normalized = (currency or "").upper()
    if normalized == "USD":
        return info.common_price_usd
    if normalized == "EUR":
        return info.common_price_eur
    if normalized == "UAH":
        return info.common_price_uah
    return info.common_price_rur


@dataclass(slots=True)
class Product:
    id: int
    name: str | None = None
    price: float | None = None
    currency: str | None = None
    url: str | None = None
    description: str | None = None
    add_info: str | None = None
    in_stock: int | None = None
    num_in_stock: int | None = None
    visible: bool | None = None
    sales_count: int | None = None
    returns_count: int | None = None
    good_reviews: int | None = None
    bad_reviews: int | None = None
    has_discount: bool | None = None
    sale_price: float | None = None
    sale_percent: str | float | None = None
    sale_end: datetime | None = None
    category_id: int | None = None

    _client: GGsel | None = field(default=None, repr=False, init=False, compare=False)

    @classmethod
    def from_row(cls, row: ProductRow) -> Product:
        sale = row.sale_info
        return cls(
            id=row.id_goods,
            name=row.name_goods,
            price=_as_float(row.price),
            currency=row.currency,
            description=row.info_goods,
            add_info=row.add_info,
            in_stock=row.in_stock,
            num_in_stock=row.num_in_stock,
            visible=bool(row.visible) if row.visible is not None else None,
            sales_count=row.cnt_sell,
            returns_count=row.cnt_return,
            good_reviews=row.cnt_goodresponses,
            bad_reviews=row.cnt_badresponses,
            has_discount=row.has_discount,
            sale_price=_sale_price(sale, row.currency),
            sale_percent=sale.sale_percent if sale is not None else None,
            sale_end=sale.sale_end if sale is not None else None,
        )

    @classmethod
    def from_data(cls, data: ProductData) -> Product:
        sale = data.sale_info
        statistics = data.statistics
        return cls(
            id=data.id or 0,
            name=data.name,
            price=data.price,
            currency=data.currency,
            url=data.url,
            description=data.info or data.text,
            add_info=data.add_info,
            in_stock=data.num_in_stock,
            num_in_stock=data.num_in_stock,
            visible=bool(data.is_available) if data.is_available is not None else None,
            sales_count=statistics.sales if statistics is not None else None,
            returns_count=statistics.refunds if statistics is not None else None,
            good_reviews=statistics.good_reviews if statistics is not None else None,
            bad_reviews=statistics.bad_reviews if statistics is not None else None,
            has_discount=sale is not None,
            sale_price=_sale_price(sale, data.currency),
            sale_percent=sale.sale_percent if sale is not None else None,
            sale_end=sale.sale_end if sale is not None else None,
            category_id=data.category_id,
        )

    def _require_client(self) -> GGsel:
        if self._client is None:
            raise RuntimeError(
                f"{self.__class__.__name__} is not attached to a client. "
                f"Use client.products.get() to fetch an active instance."
            )
        return self._client

    async def refresh(self) -> Product:
        return await self._require_client().products.get(self.id, force_refresh=True)

    async def update_price(
        self,
        price: float,
        *,
        variants: list[dict[str, Any]] | None = None,
    ) -> str | int | None:
        task_id = await self._require_client().products.update_price(
            self.id, price, variants=variants
        )
        self.price = price
        return task_id
