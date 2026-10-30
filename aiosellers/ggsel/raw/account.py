from __future__ import annotations

from typing import Any

from ..schemas import BalanceResponse, ReceiptsResponse
from ..transport import GGselTransport


class RawAccountService:
    def __init__(self, transport: GGselTransport):
        self._transport = transport

    async def balance(self) -> BalanceResponse:
        data = await self._transport.request(
            "get", "/api_sellers/api/sellers/account/balance/info"
        )
        return BalanceResponse.model_validate(data if isinstance(data, dict) else {})

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
    ) -> ReceiptsResponse:
        params: dict[str, Any] = {"page": page, "count": count}
        optional = {
            "currency": currency,
            "type": operation_type,
            "codeFilter": code_filter,
            "allowType": allow_type,
            "start": start,
            "finish": finish,
        }
        params.update({key: value for key, value in optional.items() if value is not None})
        data = await self._transport.request(
            "get",
            "/api_sellers/api/sellers/account/receipts",
            params=params,
        )
        return ReceiptsResponse.model_validate(data if isinstance(data, dict) else {})
