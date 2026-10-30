from __future__ import annotations

from .basic import ApiModel, RetvalResponse


class CategorySchema(ApiModel):
    id: int
    name: str | None = None
    sub: list[int] = []
    cnt: int | None = None


class CategoriesResponse(RetvalResponse):
    category: list[CategorySchema] = []
