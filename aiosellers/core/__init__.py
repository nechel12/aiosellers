"""Shared primitives for every platform adapter."""

from .capabilities import CAPABILITIES, Capability, Platform, capabilities_for
from .events import EventKind, HubEvent, HubEventData, event_kind
from .exceptions import (
    AiosellersError,
    AuthError,
    ConfigurationError,
    RateLimitedError,
    TransientError,
)
from .hub import SellerClient, SellerHub, Session
from .media_policy import MEDIA_ROOTS_ENV, MediaPathNotAllowedError, open_media, resolve_media_path
from .seller_session import SellerSession
from .state import MemoryStateStore, SQLiteStateStore, StateStore

__all__ = [
    "AiosellersError",
    "AuthError",
    "CAPABILITIES",
    "MEDIA_ROOTS_ENV",
    "Capability",
    "ConfigurationError",
    "EventKind",
    "HubEvent",
    "HubEventData",
    "MediaPathNotAllowedError",
    "MemoryStateStore",
    "Platform",
    "RateLimitedError",
    "SQLiteStateStore",
    "SellerClient",
    "SellerHub",
    "SellerSession",
    "Session",
    "StateStore",
    "TransientError",
    "capabilities_for",
    "event_kind",
    "open_media",
    "resolve_media_path",
]
