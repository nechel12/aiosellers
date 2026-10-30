from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .entities.chat import Chat, ChatMessage
from .entities.review import Review
from .entities.sale import Sale
from .schemas import EventTypes

if TYPE_CHECKING:
    from .ggsel import GGsel
else:
    GGsel = Any


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class InitialChatEvent:
    """A chat that already existed when polling started."""

    client: GGsel
    chat: Chat
    occurred_at: datetime = field(default_factory=_now)
    type: EventTypes = EventTypes.INITIAL_CHAT


@dataclass(slots=True)
class NewMessageEvent:
    client: GGsel
    chat: Chat
    message: ChatMessage
    occurred_at: datetime = field(default_factory=_now)
    type: EventTypes = EventTypes.NEW_MESSAGE


@dataclass(slots=True)
class NewSaleEvent:
    client: GGsel
    sale: Sale
    occurred_at: datetime = field(default_factory=_now)
    type: EventTypes = EventTypes.NEW_SALE


@dataclass(slots=True)
class NewReviewEvent:
    client: GGsel
    review: Review
    occurred_at: datetime = field(default_factory=_now)
    type: EventTypes = EventTypes.NEW_REVIEW


GGselEvent = InitialChatEvent | NewMessageEvent | NewSaleEvent | NewReviewEvent
