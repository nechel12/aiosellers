from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from ..core.exceptions import RequestFailedError
from ..entities.product import Product
from ..schemas import TaskStatusResponse

if TYPE_CHECKING:  # pragma: no cover
    from ..ggsel import GGsel


class ProductAPI:
    def __init__(self, client: GGsel) -> None:
        self._client = client

    def _remember(self, product: Product) -> Product:
        return self._client.remember("products", product.id, product)

    async def list(
        self,
        *,
        limit: int = 50,
        page: int = 1,
        ids: builtins.list[int] | None = None,
    ) -> builtins.list[Product]:
        result: builtins.list[Product] = []
        current_page = max(1, page)
        while len(result) < limit:
            response = await self._client._require_raw().products.list_products(
                ids=ids,
                page=current_page,
                count=min(50, limit - len(result)),
            )
            if not response.rows:
                break
            for row in response.rows:
                result.append(self._remember(Product.from_row(row)))
                if len(result) >= limit:
                    break
            if response.has_next_page is False:
                break
            if response.total_pages is not None and current_page >= response.total_pages:
                break
            current_page += 1
        return result[:limit]

    async def my(
        self,
        *,
        limit: int = 100,
        page: int = 1,
        currency: str = "RUB",
        show_hidden: bool = False,
    ) -> builtins.list[Product]:
        seller_id = self._client.seller_id
        if seller_id is None:
            raise RequestFailedError("GGsel seller id is not known yet")
        result: builtins.list[Product] = []
        current_page = max(1, page)
        while len(result) < limit:
            response = await self._client._require_raw().products.seller_goods(
                seller_id,
                page=current_page,
                rows=min(100, limit - len(result)),
                currency=currency,
                lang=self._client._config.locale,
                show_hidden=show_hidden,
            )
            if not response.rows:
                break
            for row in response.rows:
                result.append(self._remember(Product.from_row(row)))
                if len(result) >= limit:
                    break
            if response.pages is not None and current_page >= response.pages:
                break
            current_page += 1
        return result[:limit]

    async def get(self, product_id: int, *, force_refresh: bool = False) -> Product:
        if not force_refresh:
            cached = self._client.cached("products", product_id)
            if cached is not None:
                return cached

        response = await self._client._require_raw().products.get_product(product_id)
        if response.product is None:
            raise RequestFailedError(f"GGsel product {product_id} was not found")
        return self._remember(Product.from_data(response.product))

    async def update_price(
        self,
        product_id: int,
        price: float,
        *,
        variants: builtins.list[dict[str, Any]] | None = None,
    ) -> str | int | None:
        item: dict[str, Any] = {"product_id": product_id, "price": price}
        if variants:
            item["variants"] = variants
        return await self.update_prices([item])

    async def update_prices(self, items: builtins.list[dict[str, Any]]) -> str | int | None:
        if not items:
            raise ValueError("At least one price update is required")
        response = await self._client._require_raw().products.update_prices(items)
        return response.task_id

    async def task_status(self, task_id: int | str) -> TaskStatusResponse:
        return await self._client._require_raw().products.task_status(task_id)
