from __future__ import annotations

from typing import Any

from ..schemas import ReviewsResponse
from ..transport import GGselTransport


class RawReviewService:
    def __init__(self, transport: GGselTransport):
        self._transport = transport

    async def reviews(
        self,
        *,
        review_type: str = "all",
        page: int = 1,
        count: int = 10,
        product_id: int | None = None,
    ) -> ReviewsResponse:
        params: dict[str, Any] = {"type": review_type, "page": page, "count": count}
        if product_id is not None:
            params["product_id"] = product_id
        data = await self._transport.request("get", "/api_sellers/api/reviews", params=params)
        return ReviewsResponse.model_validate(data if isinstance(data, dict) else {})
