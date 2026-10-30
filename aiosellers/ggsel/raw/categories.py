from __future__ import annotations

from typing import Any

from ..schemas import CategoriesResponse
from ..transport import GGselTransport


class RawCategoryService:
    def __init__(self, transport: GGselTransport):
        self._transport = transport

    async def categories(
        self,
        *,
        page: int = 1,
        count: int = 10,
        category_id: int | None = None,
    ) -> CategoriesResponse:
        params: dict[str, Any] = {"page": page, "count": count}
        if category_id is not None:
            params["category_id"] = category_id
        data = await self._transport.request("get", "/api_sellers/api/categories", params=params)
        return CategoriesResponse.model_validate(data if isinstance(data, dict) else {})
