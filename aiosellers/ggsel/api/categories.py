from __future__ import annotations

import builtins
from typing import TYPE_CHECKING

from ..entities.category import Category

if TYPE_CHECKING:  # pragma: no cover
    from ..ggsel import GGsel


class CategoryAPI:
    def __init__(self, client: GGsel) -> None:
        self._client = client

    async def list(
        self,
        *,
        limit: int = 100,
        page: int = 1,
        category_id: int | None = None,
    ) -> builtins.list[Category]:
        result: builtins.list[Category] = []
        seen: set[int] = set()
        current_page = max(1, page)
        while len(result) < limit:
            want = min(100, limit - len(result))
            response = await self._client._require_raw().categories.categories(
                page=current_page,
                count=want,
                category_id=category_id,
            )
            if not response.category:
                break
            added = 0
            for schema in response.category:
                if schema.id in seen:
                    continue
                seen.add(schema.id)
                added += 1
                result.append(
                    Category(
                        id=schema.id,
                        name=schema.name,
                        sub_ids=list(schema.sub),
                        count=schema.cnt,
                    )
                )
                if len(result) >= limit:
                    break
            if added == 0:
                break
            current_page += 1
        return result[:limit]
