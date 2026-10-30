"""Shared primitives for every platform adapter."""

from .capabilities import CAPABILITIES, Capability, Platform, capabilities_for
from .events import EventKind, HubEvent, event_kind
from .hub import SellerClient, SellerHub, Session
from .state import MemoryStateStore, SQLiteStateStore, StateStore

__all__ = [
    "CAPABILITIES",
    "Capability",
    "EventKind",
    "HubEvent",
    "MemoryStateStore",
    "Platform",
    "SQLiteStateStore",
    "SellerClient",
    "SellerHub",
    "Session",
    "StateStore",
    "capabilities_for",
    "event_kind",
]
