"""Simple identity map for maintaining object identity within a session."""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class IdentityMap(Generic[K, V]):
    def __init__(self) -> None:
        self._items: dict[K, V] = {}

    def get(self, key: K) -> V | None:
        return self._items.get(key)

    def set(self, key: K, value: V) -> V:
        self._items[key] = value
        return value

    def get_or_create(self, key: K, factory: Callable[[], V]) -> V:
        if key not in self._items:
            self._items[key] = factory()
        return self._items[key]

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key: K) -> bool:
        return key in self._items
