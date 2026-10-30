from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator, cast

from pydantic import ValidationError

from ..core.state import StateStore
from .documents import CHAT_MESSAGE_CREATED, CHAT_UPDATED, USER_UPDATED
from .events import (
    _DEAL_EVENT,
    ChatInitializedEvent,
    NewMessageEvent,
    NewReviewEvent,
    PlayerokEvent,
)
from .schemas import Chat as ChatSchema
from .schemas import ChatMessage as ChatMessageSchema
from .schemas import EventTypes

if TYPE_CHECKING:
    from .playerok import Playerok

logger = logging.getLogger("aiosellers.playerok.listener")

_WS_URL = "wss://ws.playerok.com/graphql"
_WS_ACK_TIMEOUT = 15.0
_WS_RECONNECT_INITIAL = 1.0
_WS_RECONNECT_MAX = 30.0
_STOP = object()
_DRIFT_WARNED: set[tuple[str, str]] = set()


def _warn_drift(kind: str, exc: ValidationError) -> None:
    details = exc.errors()
    first: dict[str, Any] = dict(details[0]) if details else {}
    location = ".".join(str(part) for part in first.get("loc", ())) or first.get("type", "?")
    signature = (kind, location)
    if signature in _DRIFT_WARNED:
        return
    _DRIFT_WARNED.add(signature)
    logger.warning(
        "Playerok %s payload no longer matches the schema at %s (%s); falling back to partial data",
        kind,
        location,
        first.get("msg", first.get("type", "unknown")),
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def classify_message(text: str | None) -> list[EventTypes]:
    if not text:
        return []
    if text == "{{ITEM_PAID}}":
        return [EventTypes.NEW_DEAL, EventTypes.ITEM_PAID]
    if text == "{{ITEM_SENT}}":
        return [EventTypes.ITEM_SENT, EventTypes.DEAL_STATUS_CHANGED]
    if text.startswith("{{DEAL_CONFIRMED") and text.endswith("}}"):
        kind = (
            EventTypes.DEAL_CONFIRMED_AUTOMATICALLY
            if "AUTOMATICALLY" in text
            else EventTypes.DEAL_CONFIRMED
        )
        return [kind, EventTypes.DEAL_STATUS_CHANGED]
    if text == "{{DEAL_ROLLED_BACK}}":
        return [EventTypes.DEAL_ROLLED_BACK, EventTypes.DEAL_STATUS_CHANGED]
    if text == "{{DEAL_HAS_PROBLEM}}":
        return [EventTypes.DEAL_HAS_PROBLEM, EventTypes.DEAL_STATUS_CHANGED]
    if text == "{{DEAL_PROBLEM_RESOLVED}}":
        return [EventTypes.DEAL_PROBLEM_RESOLVED, EventTypes.DEAL_STATUS_CHANGED]
    return [EventTypes.NEW_MESSAGE]


def parse_chat_message(data: dict[str, Any]) -> ChatMessageSchema:
    try:
        return ChatMessageSchema.model_validate(data)
    except ValidationError as exc:
        _warn_drift("chat message", exc)
    slim: dict[str, Any] = {
        "id": data.get("id"),
        "text": data.get("text"),
        "createdAt": data.get("createdAt"),
        "isRead": bool(data.get("isRead", False)),
    }
    user = data.get("user")
    if isinstance(user, dict) and user.get("id") and user.get("username"):
        slim["user"] = {
            "id": user["id"],
            "username": user["username"],
            "role": user.get("role") or "USER",
        }
    deal = data.get("deal")
    if isinstance(deal, dict) and deal.get("id") and deal.get("status") and deal.get("direction"):
        slim_deal: dict[str, Any] = {
            "id": deal["id"],
            "status": deal["status"],
            "direction": deal["direction"],
            "hasProblem": deal.get("hasProblem", False),
        }
        chat = deal.get("chat")
        if isinstance(chat, dict) and chat.get("id"):
            slim_deal["chat"] = {"id": chat["id"]}
        item = deal.get("item")
        if isinstance(item, dict) and item.get("id"):
            kept_item: dict[str, Any] = {
                "id": item.get("id"),
                "name": item.get("name"),
                "slug": item.get("slug"),
                "price": item.get("price"),
                "rawPrice": item.get("rawPrice"),
                "sellerType": item.get("sellerType"),
            }
            item_user = item.get("user")
            if isinstance(item_user, dict) and item_user.get("id") and item_user.get("username"):
                kept_item["user"] = {
                    "id": item_user["id"],
                    "username": item_user["username"],
                    "role": item_user.get("role") or "USER",
                }
            category = item.get("category")
            if isinstance(category, dict) and category.get("id"):
                kept_item["category"] = {"id": category["id"]}
            slim_deal["item"] = kept_item
        review = deal.get("testimonial")
        if isinstance(review, dict) and review.get("id"):
            slim_deal["testimonial"] = {
                "id": review.get("id"),
                "status": review.get("status"),
                "text": review.get("text"),
                "rating": review.get("rating"),
                "createdAt": review.get("createdAt"),
                "updatedAt": review.get("updatedAt"),
            }
        slim["deal"] = slim_deal
    return ChatMessageSchema.model_validate(slim)


def parse_chat(data: dict[str, Any]) -> ChatSchema:
    try:
        return ChatSchema.model_validate(data)
    except ValidationError as exc:
        _warn_drift("chat", exc)
    slim = {"id": data.get("id"), "type": data.get("type") or "PM"}
    last = data.get("lastMessage")
    if isinstance(last, dict):
        slim["lastMessage"] = parse_chat_message(last).model_dump(by_alias=True)
    return ChatSchema.model_validate(slim)


class EventListener:
    """Realtime Playerok feed: GraphQL subscriptions plus system-message parsing."""

    def __init__(
        self,
        client: Playerok,
        *,
        refetch_message_delay: float = 6.0,
        refetch_deal_delay: float = 3.0,
        refetch_attempts: int = 3,
        history_grace_seconds: float = 90.0,
        new_chat_pause: float = 8.0,
        review_delay: float = 30.0,
        review_tries: int = 30,
        review_refresh_interval: float = 300.0,
        state: StateStore | None = None,
        processed_history_limit: int = 300,
    ) -> None:
        self.client = client
        self.refetch_message_delay = refetch_message_delay
        self.refetch_deal_delay = refetch_deal_delay
        self.refetch_attempts = refetch_attempts
        self.history_grace_seconds = history_grace_seconds
        self.new_chat_pause = new_chat_pause
        self.review_delay = review_delay
        self.review_tries = review_tries
        self.review_refresh_interval = review_refresh_interval
        self.state = state
        self.processed_history_limit = max(1, processed_history_limit)

        self.sent: list[str] = []
        self.processed_message_ids: set[str] = set()
        self._processed_order: deque[str] = deque()
        self.processed_deal_ids: set[str] = set()
        self.known_deal_ids: set[str] = set()
        self._deals_baseline_ready = False
        self.review_deal_ids: list[str] = []
        self.review_checks: dict[str, dict[str, float | int]] = {}
        self.known_chat_ids: set[str] = set()
        self._needs_resync = False
        self._chats: dict[str, ChatSchema] = {}
        self.chat_subscriptions: dict[str, str] = {}
        self._control_subscriptions: dict[str, tuple[str, str, dict[str, Any]]] = {}
        self._possible_new_chat = asyncio.Event()
        self._stop = asyncio.Event()
        self._ws: Any = None
        self._tasks: list[asyncio.Task[Any]] = []
        self._state_loaded = False
        self._state_key: str | None = None
        self._state_dirty = False
        self._state_version = 0
        self._state_lock = asyncio.Lock()

    def _raw(self) -> Any:
        raw = self.client._raw
        if raw is None:
            raise RuntimeError("Client is not started. Call start() or start_polling() first.")
        return raw

    def _me_id(self) -> str:
        me_id = self.client.me_id
        if me_id is None:
            raise RuntimeError("Client is not started. Call start() or start_polling() first.")
        return me_id

    def remember_history(self, chats: list[ChatSchema], *, now: datetime | None = None) -> None:
        moment = now or datetime.now(timezone.utc)
        for chat in chats:
            message = chat.last_message
            if message is None:
                continue
            age = (moment - _as_utc(message.created_at)).total_seconds()
            if age > self.history_grace_seconds:
                self._mark_message(message.id)

    def remember_chat(self, schema: ChatSchema) -> ChatSchema:
        previous = self._chats.get(schema.id)
        if (
            previous is not None
            and getattr(previous, "users", None)
            and not getattr(schema, "users", None)
        ):
            schema = schema.model_copy(update={"users": previous.users})
        self._chats[schema.id] = schema
        return schema

    async def _named_schema(self, schema: ChatSchema) -> ChatSchema:
        schema = self.remember_chat(schema)
        if getattr(schema, "users", None):
            return schema
        fetched = await self._raw().chats.get_chat(schema.id)
        if fetched is None or not getattr(fetched, "users", None):
            return schema
        return self.remember_chat(fetched)

    def chat_from(self, schema: ChatSchema):
        return self.client.chats._create_chat(self.remember_chat(schema))

    def subscription_frames(self) -> list[dict[str, Any]]:
        user_id = self.client.me_id
        frames = [
            self._control_frame(
                "chatUpdated",
                CHAT_UPDATED,
                {"filter": {"userId": user_id}, "showForbiddenImage": True},
            ),
            self._control_frame("userUpdated", USER_UPDATED, {"userId": user_id}),
        ]
        for chat_id in list(self.known_chat_ids):
            frames.append(self._chat_message_frame(chat_id))
        return frames

    async def handle_frame(self, data: dict[str, Any]) -> list[PlayerokEvent]:
        try:
            return await self._handle_frame(data)
        finally:
            await self._save_state()

    async def _handle_frame(self, data: dict[str, Any]) -> list[PlayerokEvent]:
        frame_type = data.get("type")

        if frame_type == "connection_ack":
            for frame in self.subscription_frames():
                await self._send(frame)
            return []

        if frame_type == "ping":
            await self._send({"type": "pong"})
            return []

        if frame_type == "pong":
            return []

        if frame_type == "connection_error":
            logger.warning("Playerok rejected the WS connection: %s", data.get("payload"))
            return []

        if frame_type == "error":
            logger.warning("Playerok subscription error: %s", data.get("payload"))
            return []

        if frame_type == "complete":
            sub_id = str(data.get("id")) if data.get("id") else None
            chat_id = self.chat_subscriptions.pop(sub_id, None) if sub_id else None
            if chat_id is not None:
                logger.debug("Subscription for chat %s completed; resubscribing", chat_id)
                await self._send(self._chat_message_frame(chat_id))
            elif sub_id is not None:
                control = self._control_subscriptions.get(sub_id)
                if control is not None:
                    operation, query, variables = control
                    await self._send(self._subscribe(operation, query, variables, sub_id=sub_id))
            return []

        payload = (data.get("payload") or {}).get("data") or {}
        events: list[PlayerokEvent] = []

        updated_user = payload.get("userUpdated")
        if isinstance(updated_user, dict) and updated_user.get("unreadChatsCounter", 0) > 0:
            self._possible_new_chat.set()

        updated_chat = payload.get("chatUpdated")
        if isinstance(updated_chat, dict):
            events.extend(await self._on_chat_updated(updated_chat))

        created = payload.get("chatMessageCreated")
        if isinstance(created, dict):
            chat_id = self.chat_subscriptions.get(str(data.get("id")))
            if chat_id is None:
                logger.debug("chatMessageCreated for an unknown subscription")
            else:
                message = parse_chat_message(created)
                known = self._chats.get(chat_id)
                schema = known or ChatSchema.model_validate({"id": chat_id, "type": "PM"})
                chat = self.chat_from(await self._named_schema(schema))
                events.extend(await self.events_for_message(chat, message))
        return events

    async def poll_new_chats_once(self) -> list[PlayerokEvent]:
        if not self._possible_new_chat.is_set():
            return []
        self._possible_new_chat.clear()
        if self.new_chat_pause:
            await asyncio.sleep(self.new_chat_pause)

        page = await self._raw().chats.get_chats(
            user_id=self._me_id(), count=15, type=self._pm_type()
        )
        if page is None:
            return []

        now = datetime.now(timezone.utc)
        events: list[PlayerokEvent] = []
        for chat_schema in page.chats:
            chat_schema = self.remember_chat(chat_schema)
            message = chat_schema.last_message
            if message is None:
                continue
            fresh = (
                now - _as_utc(message.created_at)
            ).total_seconds() <= self.history_grace_seconds
            unseen = message.id not in self.processed_message_ids
            if message.text == "{{ITEM_PAID}}" and fresh:
                chat = self.client.chats._create_chat(chat_schema)
                events.extend(await self.events_for_message(chat, message))
                continue
            if chat_schema.id not in self.known_chat_ids or unseen or fresh:
                events.extend(await self._scan_recent_paid(chat_schema, now))
        return events

    async def poll_reviews_once(self) -> list[PlayerokEvent]:
        await self._ensure_state_loaded()
        events: list[PlayerokEvent] = []
        for deal_id in list(self.review_deal_ids):
            if not self._should_check_review(deal_id):
                continue
            schema = await self._raw().deals.get_deal(deal_id)
            if schema is None or schema.review is None:
                continue
            deal = self.client.deals._create_deal(schema)
            chat = None
            if deal.chat_id:
                chat = await self.client.chats.get(deal.chat_id)
            if chat is None and schema.chat is not None:
                chat = self.client.chats._create_chat(schema.chat)
            if chat is None:
                continue
            events.append(NewReviewEvent(client=self.client, chat=chat, deal=deal))
            self.review_deal_ids.remove(deal_id)
            self._mark_state_dirty()
        await self._save_state()
        return events

    async def events_for_message(self, chat, message: ChatMessageSchema) -> list[PlayerokEvent]:
        await self._ensure_state_loaded()
        try:
            return await self._message_events(chat, message)
        finally:
            await self._save_state()

    async def _message_events(self, chat, message: ChatMessageSchema) -> list[PlayerokEvent]:
        if not message.text:
            return []
        if message.id in self.processed_message_ids:
            return []

        kinds = classify_message(message.text)
        if kinds == [EventTypes.NEW_MESSAGE]:
            event = NewMessageEvent(
                client=self.client,
                chat=chat,
                message=self.client.chats.messages._create_message(message, chat.id),
            )
            self._mark_message(message.id)
            return [event]

        actual = await self._refetch_message(chat.id, message.id) or message
        deal_schema = actual.deal
        if deal_schema is None or not deal_schema.id:
            return []
        if EventTypes.NEW_DEAL in kinds and deal_schema.id in self.processed_deal_ids:
            self._mark_message(message.id)
            return []

        fetched = await self._refetch_deal(deal_schema.id)
        if fetched is not None:
            deal_schema = fetched
        deal = self.client.deals._create_deal(deal_schema)
        entity_message = self.client.chats.messages._create_message(actual, chat.id)
        events: list[PlayerokEvent] = []
        for kind in kinds:
            event_cls = _DEAL_EVENT[kind]
            events.append(
                cast(
                    PlayerokEvent,
                    event_cls(
                        client=self.client,
                        chat=chat,
                        deal=deal,
                        message=entity_message,
                    ),
                )
            )

        if EventTypes.NEW_DEAL in kinds:
            self.processed_deal_ids.add(deal_schema.id)
            self.known_deal_ids.add(deal_schema.id)
            if deal_schema.id not in self.review_deal_ids:
                self.review_deal_ids.append(deal_schema.id)
        self._mark_message(message.id)
        return events

    async def listen(
        self, *, messages: bool = True, reviews: bool = True
    ) -> AsyncIterator[PlayerokEvent]:
        if not messages and not reviews:
            return
        await self._ensure_state_loaded()

        queue: asyncio.Queue[Any] = asyncio.Queue()

        async def produce(iterator: AsyncIterator[PlayerokEvent]) -> None:
            try:
                async for event in iterator:
                    await queue.put(event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Event feed task failed")

        tasks: list[asyncio.Task[Any]] = []
        if messages:
            page = await self._raw().chats.get_chats(user_id=self._me_id(), count=24)
            chats = list(page.chats) if page is not None else []
            self.remember_history(chats)
            for chat_schema in chats:
                chat_schema = self.remember_chat(chat_schema)
                self.known_chat_ids.add(chat_schema.id)
                chat = self.client.chats._create_chat(chat_schema)
                await queue.put(ChatInitializedEvent(client=self.client, chat=chat))
            await self._save_state()
            tasks.append(asyncio.create_task(produce(self._socket_events())))
            tasks.append(asyncio.create_task(produce(self._new_chat_events())))
        if reviews:
            tasks.append(asyncio.create_task(produce(self._review_events())))
        self._tasks = tasks

        try:
            while not self._stop.is_set():
                item = await queue.get()
                if item is _STOP:
                    break
                yield item
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        self._stop.set()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()
        await self._save_state()
        ws = self._ws
        self._ws = None
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()

    async def _socket_events(self) -> AsyncIterator[PlayerokEvent]:
        import websockets

        delay = _WS_RECONNECT_INITIAL
        while not self._stop.is_set():
            connected = False
            try:
                connect = websockets.connect(
                    _WS_URL,
                    subprotocols=[cast(Any, "graphql-transport-ws")],
                    additional_headers=self._headers(),
                    origin=cast(Any, "https://playerok.com"),
                )
                async with connect as ws:
                    self._ws = ws
                    await self._send(
                        {
                            "type": "connection_init",
                            "payload": {
                                "x-gql-op": "ws-subscription",
                                "x-gql-path": "/chats/[id]",
                                "x-timezone-offset": -180,
                            },
                        }
                    )
                    ack_deadline = asyncio.get_running_loop().time() + _WS_ACK_TIMEOUT
                    while not self._stop.is_set():
                        if connected:
                            raw = await ws.recv()
                        else:
                            remaining = ack_deadline - asyncio.get_running_loop().time()
                            if remaining <= 0:
                                raise TimeoutError("Timed out waiting for WebSocket connection_ack")
                            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        events = await self.handle_frame(data)
                        frame_type = data.get("type")
                        if frame_type in {"connection_error", "error"}:
                            raise ConnectionError(f"WebSocket {frame_type}")
                        if frame_type == "connection_ack":
                            connected = True
                            if self._needs_resync:
                                self._needs_resync = False
                                events.extend(await self._resync())
                        for event in events:
                            yield event
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("WebSocket connection dropped", exc_info=True)
            finally:
                self._ws = None

            if self._stop.is_set():
                break
            if connected:
                self._needs_resync = True
                delay = _WS_RECONNECT_INITIAL
            await asyncio.sleep(delay * random.uniform(0.5, 1.5))
            delay = min(_WS_RECONNECT_MAX, delay * 2)

    async def _resync(self) -> list[PlayerokEvent]:
        """Pull recent chats after a reconnect: WS does not replay events missed during the gap."""
        try:
            page = await self._raw().chats.get_chats(
                user_id=self._me_id(), count=24, type=self._pm_type()
            )
        except Exception:
            logger.warning("Playerok resync after reconnect failed", exc_info=True)
            return []
        if page is None:
            return []

        now = datetime.now(timezone.utc)
        events: list[PlayerokEvent] = []
        for chat_schema in page.chats:
            try:
                chat_schema = self.remember_chat(chat_schema)
                chat = self.client.chats._create_chat(chat_schema)
                if chat_schema.id not in self.known_chat_ids:
                    self.known_chat_ids.add(chat_schema.id)
                    await self._send(self._chat_message_frame(chat_schema.id))
                    events.append(ChatInitializedEvent(client=self.client, chat=chat))
                events.extend(await self._scan_recent_paid(chat_schema, now))
                message = chat_schema.last_message
                if message is not None:
                    age = (now - _as_utc(message.created_at)).total_seconds()
                    if age <= self.history_grace_seconds:
                        events.extend(await self.events_for_message(chat, message))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("Playerok resync failed for chat %s", chat_schema.id, exc_info=True)
        return events

    async def _new_chat_events(self) -> AsyncIterator[PlayerokEvent]:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._possible_new_chat.wait(), timeout=15)
            except TimeoutError:
                pass
            except asyncio.CancelledError:
                raise
            if self._stop.is_set():
                break
            try:
                for event in await self.poll_new_chats_once():
                    yield event
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("New chat poll failed", exc_info=True)

    async def _review_events(self) -> AsyncIterator[PlayerokEvent]:
        last_refresh = 0.0
        while not self._stop.is_set():
            now = asyncio.get_running_loop().time()
            if not self._deals_baseline_ready or (
                self.review_refresh_interval and now - last_refresh >= self.review_refresh_interval
            ):
                last_refresh = now
                try:
                    await self._refresh_known_deals()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.debug("Deal refresh for review polling failed", exc_info=True)
            try:
                for event in await self.poll_reviews_once():
                    yield event
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("Review poll failed", exc_info=True)
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise

    async def _refresh_known_deals(self) -> None:
        """Track deals seen by the feed so review polling does not depend on message events."""
        await self._ensure_state_loaded()
        try:
            await self._refresh_deals_from_feed()
        finally:
            await self._save_state()

    async def _refresh_deals_from_feed(self) -> None:
        response = await self._raw().deals.get_deals(user_id=self._me_id(), count=24)
        if response is None:
            return

        deal_ids = [schema.id for schema in response.deals]
        if not self._deals_baseline_ready:
            # Deals that already existed at startup are not "new"; their reviews
            # (if any) must not be reported as fresh events.
            self.known_deal_ids.update(deal_ids)
            self._deals_baseline_ready = True
            self._mark_state_dirty()
            return

        for deal_id in deal_ids:
            if deal_id in self.known_deal_ids or deal_id in self.processed_deal_ids:
                continue
            self.known_deal_ids.add(deal_id)
            if deal_id not in self.review_deal_ids:
                self.review_deal_ids.append(deal_id)
            self._mark_state_dirty()

    async def _on_chat_updated(self, data: dict[str, Any]) -> list[PlayerokEvent]:
        chat_schema = await self._named_schema(parse_chat(data))
        events: list[PlayerokEvent] = []
        if chat_schema.id not in self.chat_subscriptions.values():
            await self._send(self._chat_message_frame(chat_schema.id))
            chat = self.chat_from(chat_schema)
            self.known_chat_ids.add(chat_schema.id)
            events.append(ChatInitializedEvent(client=self.client, chat=chat))
            if chat_schema.last_message is not None:
                events.extend(await self.events_for_message(chat, chat_schema.last_message))
        return events

    async def _scan_recent_paid(
        self, chat_schema: ChatSchema, now: datetime
    ) -> list[PlayerokEvent]:
        page = await self._raw().chats.get_chat_messages(chat_schema.id, count=12)
        if page is None:
            return []
        for message in page.messages:
            if message.text != "{{ITEM_PAID}}":
                continue
            age = (now - _as_utc(message.created_at)).total_seconds()
            if age > self.history_grace_seconds:
                continue
            chat = self.chat_from(chat_schema)
            self.known_chat_ids.add(chat_schema.id)
            return await self.events_for_message(chat, message)
        return []

    async def _refetch_message(self, chat_id: str, message_id: str) -> ChatMessageSchema | None:
        for _ in range(self.refetch_attempts):
            if self.refetch_message_delay:
                await asyncio.sleep(self.refetch_message_delay)
            page = await self._raw().chats.get_chat_messages(chat_id, count=12)
            if page is None:
                continue
            for message in page.messages:
                if message.id == message_id:
                    return message
        return None

    async def _refetch_deal(self, deal_id: str):
        for _ in range(self.refetch_attempts):
            try:
                deal = await self._raw().deals.get_deal(deal_id)
            except Exception:
                deal = None
            if deal is not None:
                return deal
            if self.refetch_deal_delay:
                await asyncio.sleep(self.refetch_deal_delay)
        return None

    def _should_check_review(self, deal_id: str) -> bool:
        now = asyncio.get_running_loop().time()
        info = self.review_checks.get(deal_id, {"last": 0.0, "tries": 0})
        last = float(info["last"])
        tries = int(info["tries"])
        if now - last > self.review_delay:
            self.review_checks[deal_id] = {"last": now, "tries": tries + 1}
            return True
        if tries >= self.review_tries:
            if deal_id in self.review_deal_ids:
                self.review_deal_ids.remove(deal_id)
                self._mark_state_dirty()
            self.review_checks.pop(deal_id, None)
        return False

    def _mark_message(self, message_id: str) -> None:
        if message_id in self.processed_message_ids:
            return
        self.processed_message_ids.add(message_id)
        self._processed_order.append(message_id)
        while len(self._processed_order) > self.processed_history_limit:
            oldest = self._processed_order.popleft()
            self.processed_message_ids.discard(oldest)
        self._mark_state_dirty()

    def _mark_state_dirty(self) -> None:
        self._state_dirty = True
        self._state_version += 1

    async def _ensure_state_loaded(self) -> None:
        if self.state is None or self._state_loaded:
            return
        user_id = self.client.me_id
        if user_id is None:
            return
        self._state_key = f"playerok:{user_id}:listener"
        async with self._state_lock:
            if self._state_loaded:
                return
            try:
                data = await self.state.get(self._state_key)
            except Exception as exc:
                logger.warning("Playerok state load failed: %s", exc)
                raise
            self._state_loaded = True
            if not isinstance(data, dict) or data.get("version") != 1:
                return
            try:
                self._restore_state(data)
            except (TypeError, ValueError) as exc:
                logger.warning("Playerok state is malformed, starting fresh: %s", exc)
                self._reset_state()
            else:
                self._state_dirty = False

    def _restore_state(self, data: dict[str, Any]) -> None:
        messages = self._string_list(data.get("messages"), "messages")
        messages = list(dict.fromkeys(messages))[-self.processed_history_limit :]
        processed_deals = self._string_list(data.get("processed_deals"), "processed_deals")
        known_deals = self._string_list(data.get("known_deals"), "known_deals")
        review_deals = self._string_list(data.get("review_deals"), "review_deals")
        deals_ready = bool(data.get("deals_ready"))

        self.processed_message_ids = set(messages)
        self._processed_order = deque(messages)
        self.processed_deal_ids = set(processed_deals)
        self.known_deal_ids = set(known_deals)
        self.review_deal_ids = list(dict.fromkeys(review_deals))
        self._deals_baseline_ready = deals_ready
        if messages or known_deals:
            # Recover messages missed while the process was down, the same way
            # a websocket reconnect does.
            self._needs_resync = True

    def _reset_state(self) -> None:
        self.processed_message_ids.clear()
        self._processed_order.clear()
        self.processed_deal_ids.clear()
        self.known_deal_ids.clear()
        self.review_deal_ids.clear()
        self._deals_baseline_ready = False
        self._state_dirty = False

    @staticmethod
    def _string_list(raw: Any, field: str) -> list[str]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise ValueError(f"{field} must be a list")
        return [str(item) for item in raw]

    def _snapshot(self) -> dict[str, Any]:
        return {
            "version": 1,
            "messages": list(self._processed_order),
            "processed_deals": list(self.processed_deal_ids),
            "known_deals": list(self.known_deal_ids),
            "review_deals": list(self.review_deal_ids),
            "deals_ready": self._deals_baseline_ready,
        }

    async def _save_state(self) -> None:
        if (
            self.state is None
            or not self._state_loaded
            or not self._state_dirty
            or self._state_key is None
        ):
            return
        async with self._state_lock:
            if not self._state_loaded or not self._state_dirty:
                return
            version = self._state_version
            snapshot = self._snapshot()
            try:
                await self.state.set(self._state_key, snapshot)
            except Exception as exc:
                logger.warning("Playerok state save failed: %s", exc)
                return
            if version == self._state_version:
                self._state_dirty = False

    def _subscribe(
        self, operation: str, query: str, variables: dict[str, Any], *, sub_id: str | None = None
    ) -> dict[str, Any]:
        return {
            "id": sub_id or str(uuid.uuid4()),
            "type": "subscribe",
            "payload": {
                "extensions": {},
                "operationName": operation,
                "query": query,
                "variables": variables,
            },
        }

    def _control_frame(
        self, operation: str, query: str, variables: dict[str, Any]
    ) -> dict[str, Any]:
        for sub_id, (known_op, _, _) in self._control_subscriptions.items():
            if known_op == operation:
                return self._subscribe(operation, query, variables, sub_id=sub_id)
        sub_id = str(uuid.uuid4())
        self._control_subscriptions[sub_id] = (operation, query, variables)
        return self._subscribe(operation, query, variables, sub_id=sub_id)

    def _chat_message_frame(self, chat_id: str) -> dict[str, Any]:
        for sub_id, known in self.chat_subscriptions.items():
            if known == chat_id:
                return self._subscribe(
                    "chatMessageCreated",
                    CHAT_MESSAGE_CREATED,
                    {"filter": {"chatId": chat_id}, "showForbiddenImage": True},
                    sub_id=sub_id,
                )
        sub_id = str(uuid.uuid4())
        self.chat_subscriptions[sub_id] = chat_id
        self.known_chat_ids.add(chat_id)
        return self._subscribe(
            "chatMessageCreated",
            CHAT_MESSAGE_CREATED,
            {"filter": {"chatId": chat_id}, "showForbiddenImage": True},
            sub_id=sub_id,
        )

    async def _send(self, frame: dict[str, Any]) -> None:
        raw = json.dumps(frame)
        self.sent.append(raw)
        if self._ws is not None:
            await self._ws.send(raw)

    def _headers(self) -> dict[str, str]:
        transport = self.client._transport
        token = transport._access_token if transport is not None else ""
        user_agent = transport.config.user_agent if transport is not None else "aiosellers"
        return {
            "Origin": "https://playerok.com",
            "Cookie": f"token={token}",
            "User-Agent": user_agent,
        }

    @staticmethod
    def _pm_type():
        from .schemas import ChatTypes

        return ChatTypes.PM
