from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator

from ..core.state import StateStore
from .core.exceptions import RateLimitedError, RequestFailedError, UnauthorizedError
from .entities.chat import Chat
from .events import InitialChatEvent, NewMessageEvent, NewReviewEvent, NewSaleEvent
from .schemas import ChatItem, ChatMessageSchema

if TYPE_CHECKING:
    from .ggsel import GGsel

logger = logging.getLogger("aiosellers.ggsel.listener")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else _as_utc(value).isoformat()


@dataclass(slots=True)
class _ChatState:
    last_id: int = 0
    last_at: str | None = None
    count: int | None = None


class EventListener:
    """Polling event feed for GGsel.

    GGsel has no webhooks in the V1 seller API, so chats, sales and reviews are
    polled. Chat message ids and known sale/review ids are persisted in a
    :class:`StateStore` to avoid duplicates across process restarts.
    """

    def __init__(
        self,
        client: GGsel,
        *,
        state: StateStore | None = None,
        chats_page_size: int = 50,
        chat_page_limit: int = 5,
        history_limit: int = 100,
        history_batches: int = 10,
        history_grace_seconds: float = 300.0,
        sales_top: int = 50,
        reviews_page_size: int = 50,
        state_limit: int = 1000,
        include_own: bool = False,
    ) -> None:
        self.client = client
        self.state = state
        self.chats_page_size = max(1, min(100, chats_page_size))
        self.chat_page_limit = max(1, chat_page_limit)
        self.history_limit = max(1, min(100, history_limit))
        self.history_batches = max(1, history_batches)
        self.history_grace_seconds = history_grace_seconds
        self.sales_top = max(1, min(100, sales_top))
        self.reviews_page_size = max(1, min(100, reviews_page_size))
        self.state_limit = max(1, state_limit)
        self.include_own = include_own

        self._chats: dict[int, _ChatState] = {}
        self._chats_ready = False
        self._sales: list[int] = []
        self._sales_ready = False
        self._reviews: list[int] = []
        self._reviews_ready = False

        self._state_loaded = False
        self._state_key: str | None = None
        self._state_dirty = False
        self._state_version = 0
        self._state_lock = asyncio.Lock()

    async def listen(
        self,
        *,
        messages: bool = True,
        sales: bool = True,
        reviews: bool = True,
        interval: float | None = None,
    ) -> AsyncIterator[Any]:
        pause = self.client._config.poll_interval if interval is None else interval
        while True:
            started = time.monotonic()
            events = await self.tick(messages=messages, sales=sales, reviews=reviews)
            for event in events:
                yield event
            remain = pause - (time.monotonic() - started)
            if remain > 0:
                await asyncio.sleep(remain)

    async def tick(
        self,
        *,
        messages: bool = True,
        sales: bool = True,
        reviews: bool = True,
    ) -> list[Any]:
        if self.client._transport is None:
            raise RuntimeError("Client is not started. Call start() or start_polling() first.")
        await self._ensure_state_loaded()

        events: list[Any] = []
        try:
            for enabled, collect in (
                (messages, self._chat_events),
                (sales, self._sale_events),
                (reviews, self._review_events),
            ):
                if not enabled:
                    continue
                try:
                    events.extend(await collect())
                except UnauthorizedError:
                    raise
                except RateLimitedError:
                    logger.warning("GGsel rate limited while polling")
                    break
                except RequestFailedError as exc:
                    logger.warning("GGsel poll failed: %s", exc)
        finally:
            await self._save_state()
        return events

    async def _chat_events(self) -> list[Any]:
        items = await self._chat_items()
        events: list[Any] = []

        if not self._chats_ready:
            self._chats_ready = True
            self._mark_state_dirty()
            for item in items:
                try:
                    state = await self._baseline_chat(item)
                except (RateLimitedError, RequestFailedError) as exc:
                    logger.warning("GGsel chat %s baseline failed: %s", item.id_i, exc)
                    continue
                chat = self.client.chats._to_chat(item)
                events.append(InitialChatEvent(client=self.client, chat=chat))
                self._chats[item.id_i] = state
            return events

        changed = False
        for item in items:
            known = self._chats.get(item.id_i)
            if known is None:
                chat = self.client.chats._to_chat(item)
                try:
                    state, new_events = await self._new_chat_state(item, chat)
                except (RateLimitedError, RequestFailedError) as exc:
                    logger.warning("GGsel chat %s history failed: %s", item.id_i, exc)
                    continue
                events.append(InitialChatEvent(client=self.client, chat=chat))
                events.extend(new_events)
                self._chats[item.id_i] = state
                changed = True
                continue

            if not self._chat_changed(item, known):
                continue

            try:
                rows = await self._messages_after(item.id_i, known.last_id)
            except (RateLimitedError, RequestFailedError) as exc:
                logger.warning("GGsel chat %s history failed: %s", item.id_i, exc)
                continue

            chat = self.client.chats._to_chat(item)
            for row in rows:
                if row.seller and not self.include_own:
                    continue
                message = self.client.chats._to_message(row, item.id_i)
                events.append(
                    NewMessageEvent(client=self.client, chat=chat, message=message)
                )
            last_id = max((row.id for row in rows), default=known.last_id)
            if last_id > known.last_id:
                known.last_id = last_id
            known.last_at = _iso(item.last_message)
            known.count = item.cnt_msg
            changed = True

        if changed:
            self._mark_state_dirty()
        return events

    async def _new_chat_state(
        self, item: ChatItem, chat: Chat
    ) -> tuple[_ChatState, list[Any]]:
        if not self._recent(item.last_message):
            return await self._baseline_chat(item), []

        rows = await self._messages_after(item.id_i, 0)
        events: list[Any] = []
        for row in rows:
            if row.seller and not self.include_own:
                continue
            message = self.client.chats._to_message(row, item.id_i)
            events.append(NewMessageEvent(client=self.client, chat=chat, message=message))
        state = _ChatState(
            last_id=max((row.id for row in rows), default=0),
            last_at=_iso(item.last_message),
            count=item.cnt_msg,
        )
        return state, events

    async def _chat_items(self) -> list[ChatItem]:
        raw = self.client._require_raw()
        items: list[ChatItem] = []
        seen: set[int] = set()
        page = 1
        while page <= self.chat_page_limit:
            response = await raw.chats.list_chats(page=page, page_size=self.chats_page_size)
            for item in response.items:
                if item.id_i not in seen:
                    seen.add(item.id_i)
                    items.append(item)
            if response.cnt_pages is not None and page >= response.cnt_pages:
                break
            if not response.items:
                break
            page += 1
        return items

    async def _baseline_chat(self, item: ChatItem) -> _ChatState:
        if item.cnt_msg == 0:
            return _ChatState(last_at=_iso(item.last_message), count=item.cnt_msg)
        rows = await self._client_history(item.id_i, from_id=None, count=self.history_limit)
        return _ChatState(
            last_id=max((row.id for row in rows), default=0),
            last_at=_iso(item.last_message),
            count=item.cnt_msg,
        )

    async def _messages_after(self, chat_id: int, last_id: int) -> list[ChatMessageSchema]:
        collected: dict[int, ChatMessageSchema] = {}
        cursor = last_id
        for _ in range(self.history_batches):
            rows = await self._client_history(
                chat_id,
                from_id=cursor or None,
                newer=True if cursor else None,
                count=self.history_limit,
            )
            if not rows:
                break
            fresh = [row for row in rows if row.id > cursor]
            if not fresh:
                break
            for row in fresh:
                collected[row.id] = row
            cursor = max(collected)
            if len(rows) < self.history_limit:
                break
        return [collected[key] for key in sorted(collected)]

    async def _client_history(
        self,
        chat_id: int,
        *,
        from_id: int | None,
        count: int,
        newer: bool | None = None,
    ) -> list[ChatMessageSchema]:
        return await self.client._require_raw().chats.history(
            chat_id,
            from_id=from_id,
            newer=newer,
            count=count,
        )

    def _chat_changed(self, item: ChatItem, known: _ChatState) -> bool:
        if item.cnt_new:
            return True
        if item.cnt_msg is not None and known.count is not None and item.cnt_msg != known.count:
            return True
        last_at = _iso(item.last_message)
        return last_at is not None and last_at != known.last_at

    async def _sale_events(self) -> list[Any]:
        response = await self.client._require_raw().sales.last_sales(
            top=self.sales_top,
            seller_id=self.client.seller_id,
        )
        rows = response.sales
        ids = [row.invoice_id for row in rows]
        if not self._sales_ready:
            self._sales = ids[: self.state_limit]
            self._sales_ready = True
            self._mark_state_dirty()
            return []

        known = set(self._sales)
        fresh = [row for row in rows if row.invoice_id not in known]
        if not fresh:
            return []
        seen = set(ids)
        self._sales = (ids + [sale_id for sale_id in self._sales if sale_id not in seen])[
            : self.state_limit
        ]
        self._mark_state_dirty()
        fresh.sort(key=lambda row: (row.date.timestamp() if row.date else 0.0, row.invoice_id))
        return [
            NewSaleEvent(client=self.client, sale=self.client.sales._to_sale(row))
            for row in fresh
        ]

    async def _review_events(self) -> list[Any]:
        response = await self.client._require_raw().reviews.reviews(
            page=1, count=self.reviews_page_size
        )
        rows = response.reviews
        ids = [row.id for row in rows]
        if not self._reviews_ready:
            self._reviews = ids[: self.state_limit]
            self._reviews_ready = True
            self._mark_state_dirty()
            return []

        known = set(self._reviews)
        fresh = [row for row in rows if row.id not in known]
        if not fresh:
            return []
        seen = set(ids)
        self._reviews = (
            ids + [review_id for review_id in self._reviews if review_id not in seen]
        )[: self.state_limit]
        self._mark_state_dirty()
        fresh.sort(key=lambda row: row.id)
        return [
            NewReviewEvent(client=self.client, review=self.client.reviews._to_review(row))
            for row in fresh
        ]

    def _recent(self, value: datetime | None) -> bool:
        if value is None:
            return False
        age = (datetime.now(timezone.utc) - _as_utc(value)).total_seconds()
        return age <= self.history_grace_seconds

    def _mark_state_dirty(self) -> None:
        self._state_dirty = True
        self._state_version += 1

    async def _ensure_state_loaded(self) -> None:
        if self.state is None or self._state_loaded:
            return
        seller_id = self.client.seller_id
        if seller_id is None:
            return
        self._state_loaded = True
        self._state_key = f"ggsel:{seller_id}:listener"
        try:
            data = await self.state.get(self._state_key)
        except Exception as exc:
            logger.warning("GGsel state load failed: %s", exc)
            return
        if not isinstance(data, dict) or data.get("version") != 1:
            return
        try:
            self._restore_state(data)
        except (TypeError, ValueError) as exc:
            logger.warning("GGsel state is malformed, starting fresh: %s", exc)
            self._reset_state()
        else:
            self._state_dirty = False

    def _restore_state(self, data: dict[str, Any]) -> None:
        raw_chats = data.get("chats") or {}
        if not isinstance(raw_chats, dict):
            raise ValueError("chats must be an object")
        chats: dict[int, _ChatState] = {}
        for raw_id, row in raw_chats.items():
            if not isinstance(row, dict):
                raise ValueError(f"bad chat state {raw_id!r}")
            chats[int(raw_id)] = _ChatState(
                last_id=int(row.get("last_id") or 0),
                last_at=row.get("last_at"),
                count=None if row.get("count") is None else int(row["count"]),
            )
        self._chats = chats
        self._chats_ready = bool(data.get("chats_ready"))
        self._sales = self._id_list(data.get("sales"), "sales")
        self._sales_ready = bool(data.get("sales_ready"))
        self._reviews = self._id_list(data.get("reviews"), "reviews")
        self._reviews_ready = bool(data.get("reviews_ready"))

    @staticmethod
    def _id_list(raw: Any, field: str) -> list[int]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise ValueError(f"{field} must be a list")
        return [int(value) for value in raw]

    def _reset_state(self) -> None:
        self._chats.clear()
        self._chats_ready = False
        self._sales.clear()
        self._sales_ready = False
        self._reviews.clear()
        self._reviews_ready = False
        self._state_dirty = False

    def _snapshot(self) -> dict[str, Any]:
        return {
            "version": 1,
            "chats": {
                str(chat_id): {
                    "last_id": state.last_id,
                    "last_at": state.last_at,
                    "count": state.count,
                }
                for chat_id, state in self._chats.items()
            },
            "chats_ready": self._chats_ready,
            "sales": self._sales,
            "sales_ready": self._sales_ready,
            "reviews": self._reviews,
            "reviews_ready": self._reviews_ready,
        }

    async def _save_state(self) -> None:
        if self.state is None or not self._state_dirty or self._state_key is None:
            return
        async with self._state_lock:
            if not self._state_dirty:
                return
            version = self._state_version
            snapshot = self._snapshot()
            try:
                await self.state.set(self._state_key, snapshot)
            except Exception as exc:
                logger.warning("GGsel state save failed: %s", exc)
                return
            if version == self._state_version:
                self._state_dirty = False
