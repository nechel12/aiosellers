"""Normalized events produced by the multi-platform hub."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .capabilities import Platform


class EventKind(StrEnum):
    INITIAL = "initial"
    MESSAGE = "message"
    REVIEW = "review"
    ORDER = "order"
    PURCHASE = "purchase"
    DEAL = "deal"
    LIST = "list"
    OTHER = "other"


_KINDS: dict[Platform, dict[str, EventKind]] = {
    Platform.FUNPAY: {
        "INITIAL_CHAT": EventKind.INITIAL,
        "INITIAL_ORDER": EventKind.INITIAL,
        "INITIAL_PURCHASE": EventKind.INITIAL,
        "CHATS_LIST_CHANGED": EventKind.LIST,
        "ORDERS_LIST_CHANGED": EventKind.LIST,
        "PURCHASES_LIST_CHANGED": EventKind.LIST,
        "NEW_MESSAGE": EventKind.MESSAGE,
        "LAST_CHAT_MESSAGE_CHANGED": EventKind.MESSAGE,
        "NEW_ORDER": EventKind.ORDER,
        "ORDER_STATUS_CHANGED": EventKind.ORDER,
        "ORDER_CLOSED": EventKind.ORDER,
        "ORDER_REFUNDED": EventKind.ORDER,
        "ORDER_PARTIALLY_REFUNDED": EventKind.ORDER,
        "NEW_PURCHASE": EventKind.PURCHASE,
        "PURCHASE_STATUS_CHANGED": EventKind.PURCHASE,
        "PURCHASE_CLOSED": EventKind.PURCHASE,
        "PURCHASE_REFUNDED": EventKind.PURCHASE,
        "NEW_REVIEW": EventKind.REVIEW,
        "REVIEW_CHANGED": EventKind.REVIEW,
        "REVIEW_DELETED": EventKind.REVIEW,
    },
    Platform.GGSEL: {
        "INITIAL_CHAT": EventKind.INITIAL,
        "NEW_MESSAGE": EventKind.MESSAGE,
        "NEW_SALE": EventKind.ORDER,
        "NEW_REVIEW": EventKind.REVIEW,
    },
    Platform.PLAYEROK: {
        "CHAT_INITIALIZED": EventKind.INITIAL,
        "NEW_MESSAGE": EventKind.MESSAGE,
        "NEW_DEAL": EventKind.DEAL,
        "ITEM_PAID": EventKind.DEAL,
        "ITEM_SENT": EventKind.DEAL,
        "DEAL_CONFIRMED": EventKind.DEAL,
        "DEAL_CONFIRMED_AUTOMATICALLY": EventKind.DEAL,
        "DEAL_ROLLED_BACK": EventKind.DEAL,
        "DEAL_HAS_PROBLEM": EventKind.DEAL,
        "DEAL_PROBLEM_RESOLVED": EventKind.DEAL,
        "DEAL_STATUS_CHANGED": EventKind.DEAL,
        "NEW_REVIEW": EventKind.REVIEW,
    },
}

_FALLBACK = (
    ("INITIAL", EventKind.INITIAL),
    ("REVIEW", EventKind.REVIEW),
    ("MESSAGE", EventKind.MESSAGE),
    ("PURCHASE", EventKind.PURCHASE),
    ("ORDER", EventKind.ORDER),
    ("DEAL", EventKind.DEAL),
    ("CHANGED", EventKind.LIST),
)


def event_kind(platform: Platform | str, event: Any) -> EventKind:
    """Map a platform event onto a portable kind; unknown events never break the stream."""
    name = getattr(getattr(event, "type", None), "name", "")
    known = _KINDS[Platform(platform)].get(name)
    if known is not None:
        return known
    for marker, kind in _FALLBACK:
        if marker in name:
            return kind
    return EventKind.OTHER


@dataclass(slots=True, frozen=True)
class HubEvent:
    """A platform event together with where it came from."""

    platform: Platform
    session_id: str
    kind: EventKind
    event: Any

    @property
    def client(self) -> Any:
        return getattr(self.event, "client", None)

    @property
    def type(self) -> Any:
        return getattr(self.event, "type", None)
