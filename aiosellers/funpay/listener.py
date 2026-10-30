from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, cast

from ..core.state import StateStore
from .core.utils import order_id_from, random_tag
from .events import (
    ChatsListChangedEvent,
    FunPayEvent,
    InitialChatEvent,
    InitialOrderEvent,
    InitialPurchaseEvent,
    LastChatMessageChangedEvent,
    NewMessageEvent,
    NewOrderEvent,
    NewPurchaseEvent,
    NewReviewEvent,
    OrderClosedEvent,
    OrderPartiallyRefundedEvent,
    OrderRefundedEvent,
    OrdersListChangedEvent,
    OrderStatusChangedEvent,
    PurchaseClosedEvent,
    PurchaseRefundedEvent,
    PurchasesListChangedEvent,
    PurchaseStatusChangedEvent,
    ReviewChangedEvent,
    ReviewDeletedEvent,
)
from .exceptions import (
    AccountNotInitiatedError,
    RateLimitedError,
    RequestFailedError,
    UnauthorizedError,
)
from .parsers.chats import parse_bookmarks
from .schemas import MessageTypes, OrderSide, OrderStatuses

if TYPE_CHECKING:
    from .funpay import FunPay

logger = logging.getLogger("aiosellers.funpay.listener")

_REVIEW_EVENTS = {
    MessageTypes.NEW_FEEDBACK: NewReviewEvent,
    MessageTypes.FEEDBACK_CHANGED: ReviewChangedEvent,
    MessageTypes.FEEDBACK_DELETED: ReviewDeletedEvent,
}
_POLL_ERRORS = (RequestFailedError, TimeoutError, OSError)


def message_events(client: FunPay, chat, message, *, reviews: bool) -> list[FunPayEvent]:
    """One new-message event, plus a review event when the text is a review notice."""
    events: list[FunPayEvent] = [NewMessageEvent(client=client, chat=chat, message=message)]
    if reviews:
        review_type = _REVIEW_EVENTS.get(message.type)
        if review_type is not None:
            events.append(
                cast(
                    FunPayEvent,
                    review_type(
                        client=client,
                        message=message,
                        order_id=order_id_from(message.text),
                    ),
                )
            )
    return events


class EventListener:
    """Poll FunPay runner objects. There is no websocket."""

    def __init__(
        self,
        client: FunPay,
        *,
        order_resync_interval: float = 60.0,
        order_page_limit: int = 50,
        chat_history_batches: int = 5,
        state: StateStore | None = None,
        sent_history_limit: int = 1000,
    ) -> None:
        self.client = client
        self.order_resync_interval = order_resync_interval
        self.order_page_limit = order_page_limit
        self.chat_history_batches = chat_history_batches
        self.state = state
        self.sent_history_limit = max(1, sent_history_limit)
        self.sent_ids: dict[int | str, set[int]] = {}
        self._chat_tag: str | None = None
        self._order_tag: str | None = None
        self._chats: dict[int, tuple[int, int, str]] = {}
        self._orders: dict[str, OrderStatuses] = {}
        self._purchases: dict[str, OrderStatuses] = {}
        self._chat_ready = False
        self._orders_ready = False
        self._purchases_ready = False
        self._last_counts: tuple[int, int] | None = None
        self._next_order_resync = 0.0
        self._state_loaded = False
        self._state_key: str | None = None
        self._state_dirty = False
        self._state_version = 0
        self._state_lock = asyncio.Lock()
        client._listener = self

    def remember_sent(self, chat_id: int | str, message_id: int) -> None:
        self._track_sent(chat_id, message_id)
        if isinstance(chat_id, int):
            self._track_sent(str(chat_id), message_id)
        elif chat_id.isdigit():
            self._track_sent(int(chat_id), message_id)
        self._mark_state_dirty()

    def _track_sent(self, chat_id: int | str, message_id: int) -> None:
        ids = self.sent_ids.setdefault(chat_id, set())
        ids.add(message_id)
        while len(ids) > self.sent_history_limit:
            ids.discard(min(ids))

    def was_sent(self, chat_id: int | str, message_id: int) -> bool:
        if message_id in self.sent_ids.get(chat_id, ()):
            return True
        if isinstance(chat_id, int):
            return message_id in self.sent_ids.get(str(chat_id), ())
        if isinstance(chat_id, str) and chat_id.isdigit():
            return message_id in self.sent_ids.get(int(chat_id), ())
        return False

    async def listen(
        self,
        *,
        messages: bool = True,
        orders: bool = True,
        purchases: bool = True,
        reviews: bool = True,
        interval: float | None = None,
    ):
        pause = self.client._config.poll_interval if interval is None else interval
        while True:
            started = time.monotonic()
            transport = self.client._transport
            if transport is not None and time.monotonic() < transport.rate_limited_until:
                await _sleep(pause)
                continue
            events = await self.tick(
                messages=messages, orders=orders, purchases=purchases, reviews=reviews
            )
            for event in events:
                yield event
            remain = pause - (time.monotonic() - started)
            if remain > 0:
                await _sleep(remain)

    async def tick(
        self,
        *,
        messages: bool = True,
        orders: bool = True,
        purchases: bool = True,
        reviews: bool = True,
    ):
        transport = self.client._transport
        if transport is None:
            raise RuntimeError("Client is not started. Call start() or start_polling() first.")
        try:
            await transport.refresh_profile()
        except UnauthorizedError:
            raise
        except _POLL_ERRORS as exc:
            logger.warning("FunPay session refresh failed: %s", exc)
            return []
        try:
            return await self._collect(
                messages=messages, orders=orders, purchases=purchases, reviews=reviews
            )
        except RateLimitedError:
            logger.warning("FunPay rate limited")
            return []
        except UnauthorizedError:
            raise
        except _POLL_ERRORS as exc:
            logger.warning("FunPay poll failed: %s", exc)
            return []
        finally:
            await self._save_state()

    async def _collect(self, *, messages: bool, orders: bool, purchases: bool, reviews: bool):
        account_id = self.client.account_id
        if account_id is None:
            raise AccountNotInitiatedError("account is not initiated")
        if not await self._ensure_state_loaded(account_id):
            return []
        raw = self.client._raw
        assert raw is not None
        payload = await raw.account.runner_poll(
            [
                {
                    "type": "chat_bookmarks",
                    "id": account_id,
                    "tag": self._chat_tag or random_tag(),
                    "data": False,
                },
                {
                    "type": "orders_counters",
                    "id": account_id,
                    "tag": self._order_tag or random_tag(),
                    "data": False,
                },
            ]
        )
        bookmarks = None
        counters = None
        for obj in payload.get("objects") or []:
            kind = obj.get("type")
            if obj.get("tag"):
                if kind == "chat_bookmarks":
                    self._chat_tag = obj["tag"]
                elif kind == "orders_counters":
                    self._order_tag = obj["tag"]
            if kind == "chat_bookmarks":
                bookmarks = obj
            elif kind == "orders_counters":
                counters = obj
        events = []
        if messages and bookmarks is not None:
            try:
                events.extend(await self._chat_events(bookmarks, reviews=reviews))
            except UnauthorizedError:
                raise
            except _POLL_ERRORS as exc:
                logger.warning("FunPay chat poll failed: %s", exc)
        buyer, seller = _counts(counters)
        previous = self._last_counts
        counters_known = counters is not None
        if counters_known and previous != (buyer, seller):
            self._last_counts = (buyer, seller)
            self._mark_state_dirty()

        now = time.monotonic()
        resync_due = now >= self._next_order_resync
        if resync_due:
            self._next_order_resync = now + self.order_resync_interval
        # The runner counters change only when orders are added or removed; status-only
        # transitions are caught by the periodic full resync.
        fetch_sales = orders and (
            not self._orders_ready
            or not counters_known
            or previous is None
            or resync_due
            or seller != previous[1]
        )
        fetch_purchases = purchases and (
            not self._purchases_ready
            or not counters_known
            or previous is None
            or resync_due
            or buyer != previous[0]
        )

        if fetch_sales:
            try:
                rows, complete = await self._sales_rows(raw)
            except UnauthorizedError:
                raise
            except _POLL_ERRORS as exc:
                logger.warning("FunPay sales poll failed: %s", exc)
                self._next_order_resync = 0
            else:
                events.extend(self._order_diff(rows, buyer, seller, complete=complete))
        if fetch_purchases:
            try:
                rows, complete = await self._purchase_rows(raw)
            except UnauthorizedError:
                raise
            except _POLL_ERRORS as exc:
                logger.warning("FunPay purchases poll failed: %s", exc)
                self._next_order_resync = 0
            else:
                events.extend(self._purchase_diff(rows, buyer, seller, complete=complete))
        return events

    async def _sales_rows(self, raw):
        rows = []
        seen: set[str] = set()
        cursor = None
        for _ in range(self.order_page_limit):
            cursor, batch = await raw.orders.sales(cursor, {}, retry=False)
            for row in batch:
                if row.id not in seen:
                    seen.add(row.id)
                    rows.append(row)
            if not cursor:
                return rows, True
        logger.warning("FunPay sales pagination limit (%s) reached", self.order_page_limit)
        return rows, False

    async def _purchase_rows(self, raw):
        rows = []
        seen: set[str] = set()
        cursor = None
        for _ in range(self.order_page_limit):
            cursor, batch = await raw.orders.purchases(cursor, retry=False)
            for row in batch:
                if row.id not in seen:
                    seen.add(row.id)
                    rows.append(row)
            if not cursor:
                return rows, True
        logger.warning("FunPay purchases pagination limit (%s) reached", self.order_page_limit)
        return rows, False

    async def _chat_events(self, obj: dict, *, reviews: bool):
        data = obj.get("data")
        html = data.get("html") if isinstance(data, dict) else data
        shortcuts = parse_bookmarks(
            html if isinstance(html, str) else "",
            self_id=self.client.account_id or 0,
        )
        if not self._chat_ready:
            events: list[FunPayEvent] = []
            for shortcut in shortcuts:
                events.append(
                    InitialChatEvent(
                        client=self.client, chat=self.client.chats._from_shortcut(shortcut)
                    )
                )
                self._chats[shortcut.id] = (
                    shortcut.node_message_id,
                    shortcut.user_message_id,
                    shortcut.last_message_text,
                )
            self._chat_ready = True
            self._mark_state_dirty()
            return events
        changed = []
        for shortcut in shortcuts:
            previous = self._chats.get(shortcut.id)
            stored = previous[0] if previous else 0
            if shortcut.node_message_id > stored:
                changed.append((shortcut, stored))
        if not changed:
            return []
        events = [
            ChatsListChangedEvent(
                client=self.client,
                chat=self.client.chats._from_shortcut(changed[0][0]),
            )
        ]
        raw = self.client._raw
        assert raw is not None
        for shortcut, stored in changed:
            chat = self.client.chats._from_shortcut(shortcut)
            events.append(LastChatMessageChangedEvent(client=self.client, chat=chat))
            try:
                history, complete = await self._history_since(
                    raw, shortcut.id, shortcut.node_message_id, stored
                )
            except UnauthorizedError:
                raise
            except Exception:
                logger.exception("FunPay history failed for chat %s", shortcut.id)
                # Keep the old cursor so the next tick retries the same gap.
                self._chats[shortcut.id] = (
                    stored,
                    shortcut.user_message_id,
                    shortcut.last_message_text,
                )
                self._mark_state_dirty()
                continue
            if not complete:
                # Do not emit a partial gap or advance past messages still to be fetched.
                self._chats[shortcut.id] = (
                    stored,
                    shortcut.user_message_id,
                    shortcut.last_message_text,
                )
                self._mark_state_dirty()
                continue
            for snap in history:
                message = self.client.chats._message(snap)
                events.extend(message_events(self.client, chat, message, reviews=reviews))
            self._chats[shortcut.id] = (
                max(shortcut.node_message_id, max((snap.id for snap in history), default=0)),
                shortcut.user_message_id,
                shortcut.last_message_text,
            )
            self._mark_state_dirty()
        return events

    async def _history_since(self, raw, chat_id: int, newest_id: int, stored: int):
        """Read history pages until the stored cursor is reached; one page may not cover the gap."""
        collected: dict[int, object] = {}
        last = newest_id + 1
        complete = False
        for _ in range(self.chat_history_batches):
            batch = await raw.chats.history(chat_id, last, retry=False)
            if not batch:
                complete = True
                break
            for snap in batch:
                if stored < snap.id < last:
                    collected[snap.id] = snap
            oldest = min((snap.id for snap in batch), default=None)
            if oldest is None or oldest <= stored + 1 or oldest >= last:
                complete = True
                break
            last = oldest
        return [collected[key] for key in sorted(collected)], complete

    def _order_diff(self, rows, buyer: int, seller: int, *, complete: bool = True):
        return self._diff(
            rows,
            self._orders,
            ready_name="_orders_ready",
            initial=InitialOrderEvent,
            changed=OrdersListChangedEvent,
            new=NewOrderEvent,
            status=OrderStatusChangedEvent,
            closed=OrderClosedEvent,
            refunded=OrderRefundedEvent,
            partial=OrderPartiallyRefundedEvent,
            buyer=buyer,
            seller=seller,
            complete=complete,
        )

    def _purchase_diff(self, rows, buyer: int, seller: int, *, complete: bool = True):
        return self._diff(
            rows,
            self._purchases,
            ready_name="_purchases_ready",
            initial=InitialPurchaseEvent,
            changed=PurchasesListChangedEvent,
            new=NewPurchaseEvent,
            status=PurchaseStatusChangedEvent,
            closed=PurchaseClosedEvent,
            refunded=PurchaseRefundedEvent,
            partial=None,
            buyer=buyer,
            seller=seller,
            complete=complete,
        )

    def _diff(
        self,
        rows,
        saved: dict[str, OrderStatuses],
        *,
        ready_name: str,
        initial,
        changed,
        new,
        status,
        closed,
        refunded,
        partial,
        buyer: int,
        seller: int,
        complete: bool = True,
    ):
        if not getattr(self, ready_name):
            if not complete:
                return []
            events = []
            for row in rows:
                saved[row.id] = row.status
                order = self.client.orders._from_shortcut(row)
                if row.side is OrderSide.PURCHASE:
                    order.side = OrderSide.PURCHASE
                events.append(initial(client=self.client, order=order))
            setattr(self, ready_name, True)
            self._mark_state_dirty()
            return events
        events = [changed(client=self.client, buyer_count=buyer, seller_count=seller)]
        seen: set[str] = set()
        changed_state = False
        for row in rows:
            seen.add(row.id)
            order = self.client.orders._from_shortcut(row)
            previous = saved.get(row.id)
            if previous is None:
                changed_state = True
                events.append(new(client=self.client, order=order))
                if row.status is OrderStatuses.CLOSED:
                    events.append(closed(client=self.client, order=order))
            elif previous != row.status:
                changed_state = True
                events.append(status(client=self.client, order=order))
                extra = {
                    OrderStatuses.CLOSED: closed,
                    OrderStatuses.REFUNDED: refunded,
                    OrderStatuses.PARTIALLY_REFUNDED: partial,
                }.get(row.status)
                if extra is not None:
                    events.append(extra(client=self.client, order=order))
            saved[row.id] = row.status
        if complete:
            for gone in [key for key in saved if key not in seen]:
                del saved[gone]
                changed_state = True
        if changed_state:
            self._mark_state_dirty()
        return events

    def _mark_state_dirty(self) -> None:
        self._state_dirty = True
        self._state_version += 1

    async def _ensure_state_loaded(self, account_id: int) -> bool:
        if self.state is None or self._state_loaded:
            return True
        self._state_key = f"funpay:{account_id}:listener"
        try:
            data = await self.state.get(self._state_key)
        except Exception as exc:
            logger.warning("FunPay state load failed: %s", exc)
            return False
        self._state_loaded = True
        if not isinstance(data, dict) or data.get("version") != 1:
            return True
        try:
            self._restore_state(data)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("FunPay state is malformed, starting fresh: %s", exc)
            self._reset_state()
        else:
            self._state_dirty = False
        return True

    def _reset_state(self) -> None:
        self.sent_ids.clear()
        self._chats.clear()
        self._orders.clear()
        self._purchases.clear()
        self._chat_ready = False
        self._orders_ready = False
        self._purchases_ready = False
        self._last_counts = None
        self._state_dirty = False

    def _restore_state(self, data: dict[str, Any]) -> None:
        raw_chats = data.get("chats") or {}
        if not isinstance(raw_chats, dict):
            raise ValueError("chats must be an object")
        chats: dict[int, tuple[int, int, str]] = {}
        for raw_id, row in raw_chats.items():
            if not isinstance(row, list) or len(row) != 3:
                raise ValueError(f"bad chat entry {raw_id!r}")
            chats[int(raw_id)] = (int(row[0]), int(row[1]), str(row[2]))
        orders = self._restore_statuses(data.get("orders"))
        purchases = self._restore_statuses(data.get("purchases"))
        ready = data.get("ready") or [False, False, False]
        if not isinstance(ready, list) or len(ready) != 3:
            raise ValueError("ready must hold three flags")
        counts = data.get("last_counts")
        last_counts = None if counts is None else (int(counts[0]), int(counts[1]))
        raw_sent = data.get("sent") or []
        if not isinstance(raw_sent, list):
            raise ValueError("sent must be a list")
        sent: list[tuple[int | str, int]] = []
        for entry in raw_sent:
            if not isinstance(entry, list) or len(entry) != 2:
                raise ValueError("bad sent entry")
            chat_id = entry[0]
            if isinstance(chat_id, str) and chat_id.isdigit():
                chat_id = int(chat_id)
            sent.append((chat_id, int(entry[1])))

        self._chats = chats
        self._orders = orders
        self._purchases = purchases
        self._chat_ready, self._orders_ready, self._purchases_ready = (bool(flag) for flag in ready)
        self._last_counts = last_counts
        self.sent_ids.clear()
        for chat_id, message_id in sent:
            self.remember_sent(chat_id, message_id)

    @staticmethod
    def _restore_statuses(raw: Any) -> dict[str, OrderStatuses]:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ValueError("statuses must be an object")
        return {str(order_id): OrderStatuses[name] for order_id, name in raw.items()}

    def _snapshot(self) -> dict[str, Any]:
        sent: list[list[int | str]] = []
        for chat_id, ids in self.sent_ids.items():
            if isinstance(chat_id, int) or not chat_id.isdigit():
                sent.extend([chat_id, message_id] for message_id in sorted(ids))
        return {
            "version": 1,
            "chats": {
                str(chat_id): [node_id, user_id, text]
                for chat_id, (node_id, user_id, text) in self._chats.items()
            },
            "orders": {order_id: status.name for order_id, status in self._orders.items()},
            "purchases": {order_id: status.name for order_id, status in self._purchases.items()},
            "ready": [self._chat_ready, self._orders_ready, self._purchases_ready],
            "last_counts": list(self._last_counts) if self._last_counts is not None else None,
            "sent": sent,
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
            if not self._state_dirty:
                return
            version = self._state_version
            snapshot = self._snapshot()
            try:
                await self.state.set(self._state_key, snapshot)
            except Exception as exc:
                logger.warning("FunPay state save failed: %s", exc)
                return
            if version == self._state_version:
                self._state_dirty = False


def _counts(counters: dict | None) -> tuple[int, int]:
    if not isinstance(counters, dict):
        return 0, 0
    data = counters.get("data") or {}
    if not isinstance(data, dict):
        return 0, 0
    return int(data.get("buyer") or 0), int(data.get("seller") or 0)


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)
