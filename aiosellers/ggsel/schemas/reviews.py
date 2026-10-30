from __future__ import annotations

from pydantic import Field

from .basic import ApiModel, GGselDateTime, RetvalResponse


class ReviewSchema(ApiModel):
    id: int
    info: str | None = None
    good: int | None = None
    type: str | None = None
    date: GGselDateTime | None = None
    invoice_id: int | None = None
    name: str | None = None
    comment: str | None = None
    owner_id: int | None = None


class ReviewsResponse(RetvalResponse):
    total_pages: int | None = Field(None, alias="totalPages")
    total_items: int | None = Field(None, alias="totalItems")
    total_good: int | None = Field(None, alias="totalGood")
    total_bad: int | None = Field(None, alias="totalBad")
    reviews: list[ReviewSchema] = []
