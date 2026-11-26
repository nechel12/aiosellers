"""Normalized events produced by the multi-platform hub."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal, TypedDict

from .capabilities import Platform
from .exceptions import AuthError, ConfigurationError, RateLimitedError, TransientError


class EventKind(StrEnum):
    INITIAL = "initial"
    MESSAGE = "message"
    REVIEW = "review"
    ORDER = "order"
    PURCHASE = "purchase"
    DEAL = "deal"
    LIST = "list"
    OTHER = "other"
    ERROR = "error"
    STATUS = "status"


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
        "CONNECTION_STATUS": EventKind.STATUS,
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
    if not isinstance(name, str):
        return EventKind.OTHER
    known = _KINDS[Platform(platform)].get(name)
    if known is not None:
        return known
    for marker, kind in _FALLBACK:
        if marker in name:
            return kind
    return EventKind.OTHER


class HubEventData(TypedDict):
    version: Literal[1]
    platform: str
    session_id: str
    account_id: str | None
    kind: str
    raw_type: str | None
    event_id: str | None
    occurred_at: str | None
    payload: dict[str, str | float | None]


def _id(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if type(value) is int and value != 0:
        return str(value)
    return None


@dataclass(slots=True, frozen=True)
class HubEvent:
    """A platform event together with where it came from."""

    platform: Platform
    session_id: str
    kind: EventKind
    event: Any
    account_id: str | None = None

    @property
    def client(self) -> Any:
        return getattr(self.event, "client", None)

    @property
    def type(self) -> Any:
        return getattr(self.event, "type", None)

    @property
    def error(self) -> Exception | None:
        return (
            self.event
            if self.kind is EventKind.ERROR and isinstance(self.event, Exception)
            else None
        )

    @property
    def raw_type(self) -> str | None:
        if self.kind is EventKind.ERROR:
            return "SESSION_ERROR"
        name = getattr(self.type, "name", None)
        return name if isinstance(name, str) else None

    @property
    def occurred_at(self) -> datetime | None:
        message = getattr(self.event, "message", None)
        review = getattr(self.event, "review", None)
        sale = getattr(self.event, "sale", None)
        value = (
            getattr(message, "sent_at", None)
            or getattr(review, "created_at", None)
            or getattr(review, "date", None)
            or getattr(sale, "date", None)
        )
        if isinstance(value, datetime) and value.utcoffset() is not None:
            return value.astimezone(timezone.utc)
        return None

    @property
    def event_id(self) -> str | None:
        """A persistent deduplication key where the source provides an occurrence ID."""
        if not self.account_id or not self.raw_type:
            return None
        data = self._payload()
        source = None
        if data.get("message_id"):
            source = ["message", data.get("chat_id"), data["message_id"]]
        elif self.raw_type == "NEW_REVIEW" and data.get("review_id"):
            source = ["review", data["review_id"]]
        elif self.raw_type in {"NEW_ORDER", "NEW_PURCHASE", "NEW_SALE"} and data.get("order_id"):
            source = ["order", data["order_id"]]
        if source is None:
            return None
        key = [self.platform.value, self.account_id, self.raw_type, *source]
        return "v1:" + sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()

    def _payload(self) -> dict[str, str | float | None]:
        error = self.error
        if error is not None:
            if isinstance(error, AuthError):
                code = "auth"
            elif isinstance(error, ConfigurationError):
                code = "configuration"
            elif isinstance(error, RateLimitedError):
                return {"code": "rate_limited", "retry_after": error.retry_after}
            elif isinstance(error, TransientError):
                code = "transient"
            else:
                code = "listener_failed"
            return {"code": code}

        if self.kind is EventKind.STATUS:
            state = getattr(self.event, "state", None)
            return {"state": state if isinstance(state, str) else None}

        message = getattr(self.event, "message", None)
        chat_id = _id(getattr(getattr(self.event, "chat", None), "id", None))
        payload: dict[str, str | float | None] = {}
        if chat_id is not None or message is not None:
            payload["chat_id"] = chat_id or _id(getattr(message, "chat_id", None))
        if message is not None:
            text = getattr(message, "text", None)
            payload.update(
                message_id=_id(getattr(message, "id", None)),
                sender_id=_id(
                    getattr(message, "user_id", None) or getattr(message, "author_id", None)
                ),
                text=text if isinstance(text, str) else None,
            )
        order = getattr(self.event, "order", None)
        sale = getattr(self.event, "sale", None)
        order_id = (
            _id(getattr(order, "id", None))
            or _id(getattr(sale, "invoice_id", None))
            or _id(getattr(self.event, "order_id", None))
        )
        if order_id is not None:
            payload["order_id"] = order_id
        for field in ("deal", "review"):
            value = _id(getattr(getattr(self.event, field, None), "id", None))
            if value is not None:
                payload[f"{field}_id"] = value
        return payload

    def to_dict(self) -> HubEventData:
        """Return the explicitly versioned JSON representation, never a raw object dump."""
        occurred_at = self.occurred_at
        return {
            "version": 1,
            "platform": self.platform.value,
            "session_id": self.session_id,
            "account_id": self.account_id,
            "kind": self.kind.value,
            "raw_type": self.raw_type,
            "event_id": self.event_id,
            "occurred_at": occurred_at.isoformat() if occurred_at is not None else None,
            "payload": self._payload(),
        }
