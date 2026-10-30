from __future__ import annotations

from typing import TYPE_CHECKING

from ..entities.review import Review

if TYPE_CHECKING:  # pragma: no cover
    from ..ggsel import GGsel


class ReviewAPI:
    def __init__(self, client: GGsel) -> None:
        self._client = client

    def _to_review(self, schema) -> Review:
        review = Review.from_schema(schema)
        review._client = self._client
        return review

    async def list(
        self,
        *,
        limit: int = 10,
        page: int = 1,
        review_type: str = "all",
        product_id: int | None = None,
    ) -> list[Review]:
        result: list[Review] = []
        current_page = max(1, page)
        while len(result) < limit:
            response = await self._client._require_raw().reviews.reviews(
                review_type=review_type,
                page=current_page,
                count=min(50, limit - len(result)),
                product_id=product_id,
            )
            if not response.reviews:
                break
            for schema in response.reviews:
                result.append(self._to_review(schema))
                if len(result) >= limit:
                    break
            if response.total_pages is not None and current_page >= response.total_pages:
                break
            current_page += 1
        return result[:limit]
