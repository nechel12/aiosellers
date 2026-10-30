from __future__ import annotations

from typing import Any

from ..schemas import (
    PriceUpdateResponse,
    ProductDataResponse,
    ProductListResponse,
    SellerGoodsResponse,
    TaskStatusResponse,
)
from ..transport import GGselTransport


class RawProductService:
    def __init__(self, transport: GGselTransport):
        self._transport = transport

    async def list_products(
        self,
        *,
        ids: list[int] | None = None,
        page: int = 1,
        count: int = 10,
    ) -> ProductListResponse:
        params: dict[str, Any] = {"page": page, "count": count}
        if ids:
            params["ids"] = ",".join(str(product_id) for product_id in ids)
        data = await self._transport.request(
            "get",
            "/api_sellers/api/products/list",
            params=params,
        )
        return ProductListResponse.model_validate(data if isinstance(data, dict) else {})

    async def get_product(self, product_id: int | str) -> ProductDataResponse:
        data = await self._transport.request(
            "get", f"/api_sellers/api/products/{product_id}/data"
        )
        return ProductDataResponse.model_validate(data if isinstance(data, dict) else {})

    async def seller_goods(
        self,
        seller_id: int,
        *,
        page: int = 1,
        rows: int = 100,
        currency: str = "RUB",
        lang: str = "ru-RU",
        show_hidden: bool = False,
        order_dir: str = "desc",
        owner_id: int | None = None,
    ) -> SellerGoodsResponse:
        body: dict[str, Any] = {
            "id_seller": seller_id,
            "order_col": "cntsell",
            "order_dir": order_dir,
            "rows": rows,
            "page": page,
            "currency": currency,
            "lang": lang,
            "show_hidden": int(show_hidden),
        }
        if owner_id is not None:
            body["owner_id"] = owner_id
        data = await self._transport.request(
            "post",
            "/api_sellers/api/seller-goods",
            json_body=body,
            retry=False,
        )
        return SellerGoodsResponse.model_validate(data if isinstance(data, dict) else {})

    async def update_prices(self, items: list[dict[str, Any]]) -> PriceUpdateResponse:
        data = await self._transport.request(
            "post",
            "/api_sellers/api/product/edit/prices",
            json_body=items,
            retry=False,
        )
        return PriceUpdateResponse.model_validate(data if isinstance(data, dict) else {})

    async def task_status(self, task_id: int | str) -> TaskStatusResponse:
        data = await self._transport.request(
            "get",
            "/api_sellers/api/product/edit/UpdateProductsTaskStatus",
            params={"taskId": task_id},
        )
        return TaskStatusResponse.model_validate(data if isinstance(data, dict) else {})
