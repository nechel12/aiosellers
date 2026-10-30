from __future__ import annotations

from typing import Any

from ..schemas import LastSalesResponse, PurchaseInfoResponse, UniqueCodeResponse
from ..transport import GGselTransport


class RawSaleService:
    def __init__(self, transport: GGselTransport):
        self._transport = transport

    async def last_sales(
        self,
        *,
        top: int = 10,
        group: bool | None = None,
        seller_id: int | None = None,
    ) -> LastSalesResponse:
        params: dict[str, Any] = {"top": top}
        if group is not None:
            params["group"] = "true" if group else "false"
        if seller_id is not None:
            params["seller_id"] = seller_id
        data = await self._transport.request(
            "get", "/api_sellers/api/seller-last-sales", params=params
        )
        return LastSalesResponse.model_validate(data if isinstance(data, dict) else {})

    async def purchase(self, invoice_id: int | str) -> PurchaseInfoResponse:
        data = await self._transport.request("get", f"/api_sellers/api/purchase/info/{invoice_id}")
        return PurchaseInfoResponse.model_validate(data if isinstance(data, dict) else {})

    async def purchase_by_unique_code(self, unique_code: str) -> UniqueCodeResponse:
        data = await self._transport.request(
            "get", f"/api_sellers/api/purchases/unique-code/{unique_code}"
        )
        return UniqueCodeResponse.model_validate(data if isinstance(data, dict) else {})
