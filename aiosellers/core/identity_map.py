"""Bounded identity map shared by the platform adapters.

The map exists to keep object identity stable for the same entity id while a
session lives.  A cap keeps long-running bots that browse large catalogs from
growing without bound; least-recently-used entries are evicted first.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class IdentityMap(Generic[K, V]):
    """Identity map with an optional LRU bound."""

    def __init__(self, max_items: int | None = None) -> None:
        self._items: OrderedDict[K, V] = OrderedDict()
        self._max_items = max(1, max_items) if max_items is not None else None

    def get(self, key: K) -> V | None:
        """Get a value and mark it as recently used."""
        value = self._items.get(key)
        if value is not None:
            self._items.move_to_end(key)
        return value

    def set(self, key: K, value: V) -> V:
        """Store a value, evicting the least recently used entry when needed."""
        self._items[key] = value
        self._items.move_to_end(key)
        if self._max_items is not None:
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)
        return value

    def get_or_create(self, key: K, factory: Callable[[], V]) -> V:
        """Get an existing value or create and store one."""
        value = self.get(key)
        if value is not None:
            return value
        return self.set(key, factory())

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key: K) -> bool:
        return key in self._items


__all__ = ["IdentityMap"]
