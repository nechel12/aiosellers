from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, AsyncIterator

from ..entities.chat import Chat, ChatMessage
from ..schemas import ChatItem, ChatMessageSchema

if TYPE_CHECKING:  # pragma: no cover
    from ..ggsel import GGsel


class ChatAPI:
    def __init__(self, client: GGsel) -> None:
        self._client = client

    def _to_chat(self, item: ChatItem) -> Chat:
        chat = Chat(
            id=item.id_i,
            buyer_email=item.email,
            product_id=item.product,
            last_message_at=item.last_message,
            message_count=item.cnt_msg,
            unread_count=item.cnt_new,
        )
        return self._client.remember("chats", chat.id, chat)

    @staticmethod
    def _to_message(schema: ChatMessageSchema, chat_id: int | None) -> ChatMessage:
        return ChatMessage.from_schema(schema, chat_id)

    async def list(
        self,
        *,
        limit: int = 50,
        page: int = 1,
        page_size: int | None = None,
        only_new: bool = False,
        email: str | None = None,
        product_ids: builtins.list[int] | None = None,
    ) -> builtins.list[Chat]:
        result: builtins.list[Chat] = []
        current_page = max(1, page)
        batch_size = max(1, min(100, page_size or limit or 50))

        while len(result) < limit:
            response = await self._client._require_raw().chats.list_chats(
                filter_new=True if only_new else None,
                email=email,
                product_ids=product_ids,
                page=current_page,
                page_size=batch_size,
            )
            if not response.items:
                break
            for item in response.items:
                result.append(self._to_chat(item))
                if len(result) >= limit:
                    break
            if response.cnt_pages is not None and current_page >= response.cnt_pages:
                break
            current_page += 1

        return result[:limit]

    async def iter(
        self,
        *,
        page_size: int = 50,
        only_new: bool = False,
        email: str | None = None,
        product_ids: builtins.list[int] | None = None,
    ) -> AsyncIterator[Chat]:
        current_page = 1
        while True:
            response = await self._client._require_raw().chats.list_chats(
                filter_new=True if only_new else None,
                email=email,
                product_ids=product_ids,
                page=current_page,
                page_size=page_size,
            )
            if not response.items:
                return
            for item in response.items:
                yield self._to_chat(item)
            if response.cnt_pages is not None and current_page >= response.cnt_pages:
                return
            current_page += 1

    async def get(self, chat_id: int) -> Chat | None:
        cached = self._client.cached("chats", chat_id)
        if cached is not None:
            return cached
        # The V1 API has no direct chat-by-id lookup.  Search a wider window
        # than the old hard-coded first 100 before giving up.
        chats = await self.list(limit=1000, page_size=100)
        return next((chat for chat in chats if chat.id == chat_id), None)

    async def history(
        self,
        chat_id: int | str,
        *,
        limit: int = 50,
        from_id: int | None = None,
        to_id: int | None = None,
        newer: bool | None = None,
    ) -> builtins.list[ChatMessage]:
        raw = self._client._require_raw().chats
        count = min(100, max(1, limit))
        collected: dict[int, ChatMessageSchema] = {}
        cursor_to = to_id
        while len(collected) < limit:
            rows = await raw.history(
                chat_id,
                from_id=from_id,
                to_id=cursor_to,
                newer=newer,
                count=count,
            )
            if not rows:
                break
            before = len(collected)
            for row in rows:
                collected[row.id] = row
            if len(collected) == before:
                break
            oldest = min((row.id for row in rows), default=None)
            if oldest is None or oldest <= 1:
                break
            if from_id is not None or newer:
                break
            cursor_to = oldest - 1
        messages = [self._to_message(row, int(chat_id)) for row in collected.values()]
        messages.sort(key=lambda message: message.id)
        return messages[-limit:] if limit else messages

    async def send(self, chat_id: int | str, text: str) -> None:
        if not text.strip():
            raise ValueError("Message text must not be empty")
        await self._client._require_raw().chats.send_message(chat_id, text)
