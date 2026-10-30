from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from ..schemas import ChatMessageSchema, MessageDirection

if TYPE_CHECKING:  # pragma: no cover
    from ..ggsel import GGsel


def _direction(schema: ChatMessageSchema) -> MessageDirection:
    if schema.seller:
        return MessageDirection.SELLER
    if schema.buyer:
        return MessageDirection.BUYER
    return MessageDirection.SYSTEM


@dataclass(slots=True)
class ChatMessage:
    id: int
    text: str | None = None
    direction: MessageDirection = MessageDirection.SYSTEM
    sent_at: datetime | None = None
    seen_at: datetime | None = None
    is_deleted: bool = False
    is_file: bool = False
    filename: str | None = None
    url: str | None = None
    is_image: bool = False
    preview: str | None = None
    chat_id: int | None = None

    @classmethod
    def from_schema(cls, schema: ChatMessageSchema, chat_id: int | None = None) -> ChatMessage:
        return cls(
            id=schema.id,
            text=schema.message,
            direction=_direction(schema),
            sent_at=schema.date_written,
            seen_at=schema.date_seen,
            is_deleted=bool(schema.deleted),
            is_file=bool(schema.is_file),
            filename=schema.filename,
            url=schema.url,
            is_image=bool(schema.is_img),
            preview=schema.preview,
            chat_id=chat_id,
        )

    @property
    def is_incoming(self) -> bool:
        return self.direction is MessageDirection.BUYER


@dataclass(slots=True)
class Chat:
    id: int
    buyer_email: str | None = None
    product_id: int | None = None
    last_message_at: datetime | None = None
    message_count: int | None = None
    unread_count: int | None = None

    _client: GGsel | None = field(default=None, repr=False, init=False, compare=False)

    def _require_client(self) -> GGsel:
        if self._client is None:
            raise RuntimeError(
                f"{self.__class__.__name__} is not attached to a client. "
                f"Use client.chats.list() to fetch an active instance."
            )
        return self._client

    async def get_messages(
        self,
        *,
        limit: int = 50,
        from_id: int | None = None,
        newer: bool | None = None,
    ) -> list[ChatMessage]:
        return await self._require_client().chats.history(
            self.id, limit=limit, from_id=from_id, newer=newer
        )

    async def send_text(self, text: str) -> None:
        await self._require_client().chats.send(self.id, text)
