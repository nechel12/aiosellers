from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class Category:
    id: int
    name: str | None = None
    sub_ids: list[int] = field(default_factory=list)
    count: int | None = None
