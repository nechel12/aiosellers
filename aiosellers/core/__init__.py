"""Shared primitives for every platform adapter."""

from .capabilities import CAPABILITIES, Capability, Platform, capabilities_for
from .events import EventKind, HubEvent, event_kind
from .hub import SellerClient, SellerHub, Session
from .media_policy import MEDIA_ROOTS_ENV, MediaPathNotAllowedError, open_media, resolve_media_path
from .state import MemoryStateStore, SQLiteStateStore, StateStore

__all__ = [
    "CAPABILITIES",
    "MEDIA_ROOTS_ENV",
    "Capability",
    "EventKind",
    "HubEvent",
    "MediaPathNotAllowedError",
    "MemoryStateStore",
    "Platform",
    "SQLiteStateStore",
    "SellerClient",
    "SellerHub",
    "Session",
    "StateStore",
    "capabilities_for",
    "event_kind",
    "open_media",
    "resolve_media_path",
]
