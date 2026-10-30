"""Small helpers for the loosely typed BeautifulSoup attribute API."""

from __future__ import annotations

from typing import Any


def attr(node: Any, name: str) -> str:
    """Return a single HTML attribute as text, never an AttributeValueList."""
    if node is None:
        return ""
    value = node.get(name)
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return " ".join(str(item) for item in value)
    return "" if value is None else str(value)


def attr_list(node: Any, name: str) -> list[str]:
    """Return a multi-valued HTML attribute, such as CSS classes."""
    if node is None:
        return []
    value = node.get(name)
    if isinstance(value, str):
        return value.split()
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [] if value is None else [str(value)]
