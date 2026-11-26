import asyncio
import json
import unittest
from contextlib import aclosing
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import mock

from websockets.client import ClientProtocol
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close
from websockets.server import ServerProtocol
from websockets.uri import parse_uri

from aiosellers import AuthError, MemoryStateStore, SellerHub
from aiosellers.playerok.api.chats import ChatAPI
from aiosellers.playerok.api.deals import DealAPI
from aiosellers.playerok.core.config import PlayerokConfig
from aiosellers.playerok.core.exceptions import Unauthorized
from aiosellers.playerok.events import ChatInitializedEvent, NewMessageEvent, NewReviewEvent
from aiosellers.playerok.listener import EventListener
from aiosellers.playerok.schemas import Chat as ChatSchema
from aiosellers.playerok.schemas import ChatMessage as ChatMessageSchema
from aiosellers.playerok.schemas import ItemDeal


class _RawChats:
    def __init__(self, page=None, messages=None):
        self.page = page
        self.messages = messages

    async def get_chats(self, **kwargs):
        return self.page

    async def get_chat_messages(self, chat_id, count=12):
        return self.messages

    async def get_chat(self, chat_id):
        return None


class _RawDeals:
    def __init__(self, pages=None, deals=None):
        self.pages = list(pages or [])
        self.deals = dict(deals or {})

    async def get_deals(self, **kwargs):
        if self.pages:
            return self.pages.pop(0)
        return None

    async def get_deal(self, deal_id):
        return self.deals.get(deal_id)


class _Client:
    _use_identity_map = False
    me_id = "me"
    _transport = SimpleNamespace(
        _access_token="token",
        config=SimpleNamespace(user_agent="test-agent", proxy=None),
    )

    def __init__(self, chats=None, deals=None):
        self._raw = SimpleNamespace(chats=chats or _RawChats(), deals=deals or _RawDeals())
        self.chats = ChatAPI(self)
        self.deals = DealAPI(self)

    def _require_raw(self):
        return self._raw


class _WS:
    def __init__(self):
        self.frames = []

    async def send(self, raw):
        self.frames.append(json.loads(raw))


class _Socket:
    def __init__(self, listener, frames=(), *, stop_on_enter=False, stop_after_frames=False):
        self.listener = listener
        self.frames = list(frames)
        self.stop_on_enter = stop_on_enter
        self.stop_after_frames = stop_after_frames
        self.sent = []

    async def __aenter__(self):
        if self.stop_on_enter:
            self.listener._stop.set()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def send(self, raw):
        self.sent.append(json.loads(raw))

    async def recv(self):
        if not self.frames:
            await asyncio.Future()
        frame = self.frames.pop(0)
        if not self.frames and self.stop_after_frames:
            self.listener._stop.set()
        return json.dumps(frame)


def _recent_message(message_id="m1", text="hello"):
    return {
        "id": message_id,
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "isRead": True,
    }


def _chat_page(*chats):
    return SimpleNamespace(chats=list(chats))


class FrameLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_ping_is_answered_with_pong(self):
        listener = EventListener(_Client())
        listener._ws = _WS()

        await listener.handle_frame({"type": "ping"})

        self.assertEqual(listener._ws.frames, [{"type": "pong"}])

    async def test_ack_subscribes_and_reuses_subscription_ids(self):
        listener = EventListener(_Client())
        listener.known_chat_ids.add("c1")
        listener._ws = _WS()

        await listener.handle_frame({"type": "connection_ack"})
        first = [frame["id"] for frame in listener._ws.frames]
        await listener.handle_frame({"type": "connection_ack"})
        second = [frame["id"] for frame in listener._ws.frames[len(first) :]]

        self.assertEqual(sorted(first), sorted(second))
        operations = sorted(frame["payload"]["operationName"] for frame in listener._ws.frames)
        self.assertEqual(
            operations,
            [
                "chatMessageCreated",
                "chatMessageCreated",
                "chatUpdated",
                "chatUpdated",
                "userUpdated",
                "userUpdated",
            ],
        )

    async def test_complete_resubscribes_chat_subscription(self):
        listener = EventListener(_Client())
        listener.chat_subscriptions["sub-1"] = "c1"
        listener._ws = _WS()

        await listener.handle_frame({"type": "complete", "id": "sub-1"})

        self.assertNotIn("sub-1", listener.chat_subscriptions)
        self.assertIn("c1", listener.chat_subscriptions.values())
        self.assertEqual(len(listener._ws.frames), 1)
        self.assertEqual(listener._ws.frames[0]["payload"]["operationName"], "chatMessageCreated")

    async def test_complete_resubscribes_control_subscription(self):
        listener = EventListener(_Client())
        control_id = listener.subscription_frames()[0]["id"]
        listener._ws = _WS()

        await listener.handle_frame({"type": "complete", "id": control_id})

        self.assertEqual(len(listener._ws.frames), 1)
        self.assertEqual(listener._ws.frames[0]["id"], control_id)
        self.assertEqual(listener._ws.frames[0]["type"], "subscribe")

    async def test_error_frames_do_not_break_the_stream(self):
        listener = EventListener(_Client())

        self.assertEqual(await listener.handle_frame({"type": "error", "payload": ["boom"]}), [])
        self.assertEqual(
            await listener.handle_frame({"type": "connection_error", "payload": {}}), []
        )


class SocketLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def _drain(self, listener):
        async for _ in listener._socket_events():
            pass

    async def test_ack_timeout_reconnects(self):
        listener = EventListener(_Client())
        first = _Socket(listener)
        second = _Socket(listener, stop_on_enter=True)
        with (
            mock.patch("aiosellers.playerok.listener._WS_ACK_TIMEOUT", 0.01),
            mock.patch("websockets.connect", side_effect=[first, second]) as connect,
            mock.patch(
                "aiosellers.playerok.listener.asyncio.sleep", new_callable=mock.AsyncMock
            ) as sleep,
        ):
            await asyncio.wait_for(self._drain(listener), 1)

        self.assertEqual(connect.call_count, 2)
        sleep.assert_awaited_once()

    async def test_configured_proxy_is_passed_to_websocket(self):
        listener = EventListener(_Client())
        proxy = "http://user:pass@proxy:8080"
        listener.client._transport = SimpleNamespace(
            _access_token="token",
            config=SimpleNamespace(user_agent="test-agent", proxy=proxy),
        )
        socket = _Socket(listener, stop_on_enter=True)
        with mock.patch("websockets.connect", return_value=socket) as connect:
            await asyncio.wait_for(self._drain(listener), 1)

        self.assertEqual(connect.call_args.kwargs["proxy"], proxy)

    async def test_system_proxy_is_opt_in(self):
        for enable in (False, True):
            listener = EventListener(_Client())
            listener.client._transport = SimpleNamespace(
                _access_token="token",
                config=PlayerokConfig(ws_use_system_proxy=enable),
            )
            socket = _Socket(listener, stop_on_enter=True)
            with (
                self.subTest(enable=enable),
                mock.patch("websockets.connect", return_value=socket) as connect,
            ):
                await asyncio.wait_for(self._drain(listener), 1)
                self.assertIs(connect.call_args.kwargs["proxy"], True if enable else None)

    async def test_custom_origin_and_port_produce_a_valid_handshake(self):
        listener = EventListener(_Client())
        listener.client._transport = SimpleNamespace(
            _access_token="token",
            config=PlayerokConfig(base_url="http://[::1]:8765/api/"),
        )
        socket = _Socket(listener, stop_on_enter=True)
        with mock.patch("websockets.connect", return_value=socket) as connect:
            await asyncio.wait_for(self._drain(listener), 1)

        self.assertEqual(connect.call_args.args[0], "ws://[::1]:8765/api/graphql")
        kwargs = connect.call_args.kwargs
        client = ClientProtocol(parse_uri(connect.call_args.args[0]), origin=kwargs["origin"])
        request = client.connect()
        request.headers.update(kwargs["additional_headers"])
        self.assertEqual(request.headers.get_all("Origin"), ["http://[::1]:8765"])
        self.assertEqual(ServerProtocol().accept(request).status_code, 101)

    def test_official_websocket_and_explicit_override(self):
        self.assertEqual(
            PlayerokConfig(base_url="https://playerok.com/").ws_url,
            "wss://ws.playerok.com/graphql",
        )
        self.assertEqual(
            PlayerokConfig(base_url="https://notplayerok.com/").ws_url,
            "wss://notplayerok.com/graphql",
        )
        self.assertEqual(
            PlayerokConfig(base_url="https://playerok.com/", ws_url="wss://example.test/ws").ws_url,
            "wss://example.test/ws",
        )

    async def test_connection_error_reconnects(self):
        listener = EventListener(_Client())
        first = _Socket(listener, [{"type": "connection_error", "payload": {}}])
        second = _Socket(listener, stop_on_enter=True)
        with (
            mock.patch("websockets.connect", side_effect=[first, second]) as connect,
            mock.patch(
                "aiosellers.playerok.listener.asyncio.sleep", new_callable=mock.AsyncMock
            ) as sleep,
        ):
            await asyncio.wait_for(self._drain(listener), 1)

        self.assertEqual(connect.call_count, 2)
        sleep.assert_awaited_once()

    async def test_ws_auth_error_reaches_the_hub_without_reconnect(self):
        client = _Client()
        listener = EventListener(client)
        socket = _Socket(
            listener,
            [
                {
                    "type": "connection_error",
                    "payload": {"errors": [{"extensions": {"code": "UNAUTHENTICATED"}}]},
                }
            ],
        )
        client.listen = listener.listen
        hub = SellerHub()
        hub.add(client, platform="playerok", listen_options={"reviews": False})
        with mock.patch("websockets.connect", return_value=socket) as connect:
            async with aclosing(hub.stream(error_policy="raise")) as stream:
                with self.assertRaises(AuthError):
                    await asyncio.wait_for(anext(stream), 1)
        connect.assert_called_once()
        self.assertEqual(listener._tasks, [])

    async def test_state_batching_flushes_at_idle_and_on_close(self):
        class Store(MemoryStateStore):
            def __init__(self):
                super().__init__()
                self.writes = []
                self.written = asyncio.Event()

            async def set(self, key, value):
                self.writes.append(value["messages"])
                await super().set(key, value)
                self.written.set()

        store = Store()
        listener = EventListener(_Client(), state=store, state_flush_interval=0.025)
        listener._queue = asyncio.Queue()
        listener._state_key = "fixture"
        listener._state_loaded = True
        try:
            for message in ("first", "second"):
                listener._mark_message(message)
                await listener._save_state()
            self.assertEqual(store.writes, [])
            await asyncio.wait_for(store.written.wait(), timeout=1)
            self.assertEqual(store.writes, [["first", "second"]])

            listener._mark_message("third")
            await listener._save_state()
        finally:
            await listener.aclose()
        self.assertEqual(store.writes, [["first", "second"], ["first", "second", "third"]])
        self.assertIsNone(listener._state_flush_task)

    async def test_ws_unauthorized_close_before_ack_is_fatal(self):
        listener = EventListener(_Client())
        socket = _Socket(listener)
        socket.recv = mock.AsyncMock(side_effect=ConnectionClosedError(Close(4401, ""), None))
        with mock.patch("websockets.connect", return_value=socket) as connect:
            with self.assertRaises(AuthError):
                await asyncio.wait_for(self._drain(listener), 1)
        connect.assert_called_once()

    async def test_status_events_distinguish_temporary_failure_from_auth_error(self):
        listener = EventListener(_Client(), connection_events=True)
        first = _Socket(listener, [{"type": "connection_error", "payload": {}}])
        second = _Socket(listener, [{"type": "connection_ack"}], stop_after_frames=True)
        with (
            mock.patch("websockets.connect", side_effect=[first, second]),
            mock.patch("aiosellers.playerok.listener.asyncio.sleep", new_callable=mock.AsyncMock),
        ):
            states = [event.state async for event in listener._socket_events()]
        self.assertEqual(states, ["reconnecting", "connected"])

    async def test_review_poller_forwards_auth_failure(self):
        client = _Client()
        client._raw.deals.get_deals = mock.AsyncMock(side_effect=Unauthorized("expired"))
        listener = EventListener(client)
        async with aclosing(listener.listen(messages=False, reviews=True)) as events:
            with self.assertRaises(AuthError):
                await asyncio.wait_for(anext(events), 1)
        self.assertEqual(listener._tasks, [])

    async def test_subscription_error_reconnects_and_resubscribes(self):
        listener = EventListener(_Client())
        first = _Socket(
            listener,
            [{"type": "connection_ack"}, {"type": "error", "payload": ["boom"]}],
        )
        second = _Socket(listener, [{"type": "connection_ack"}], stop_after_frames=True)
        with (
            mock.patch("websockets.connect", side_effect=[first, second]) as connect,
            mock.patch(
                "aiosellers.playerok.listener.asyncio.sleep", new_callable=mock.AsyncMock
            ) as sleep,
        ):
            await asyncio.wait_for(self._drain(listener), 1)

        self.assertEqual(connect.call_count, 2)
        operations = [
            frame["payload"]["operationName"]
            for frame in second.sent
            if frame["type"] == "subscribe"
        ]
        self.assertEqual(sorted(operations), ["chatUpdated", "userUpdated"])
        sleep.assert_awaited_once()


class ResyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_resync_fills_a_gap_behind_an_already_delivered_message(self):
        old = datetime.now(timezone.utc) - timedelta(minutes=5)
        anchor, missed, latest = [
            ChatMessageSchema.model_validate(
                _recent_message(message_id) | {"createdAt": old + timedelta(seconds=index)}
            )
            for index, message_id in enumerate(("anchor", "missed", "latest"))
        ]
        chat = ChatSchema(id="c1", type="PM", last_message=latest)
        raw = _RawChats(page=_chat_page(chat))
        raw.get_chat_messages = mock.AsyncMock(
            side_effect=[
                SimpleNamespace(
                    messages=[latest],
                    page_info=SimpleNamespace(has_next_page=True, end_cursor="page-2"),
                ),
                SimpleNamespace(messages=[missed, anchor]),
            ]
        )
        listener = EventListener(_Client(chats=raw))
        listener.processed_message_ids.update({"anchor", "latest"})

        events = await listener._resync()
        self.assertEqual(
            [event.message.id for event in events if isinstance(event, NewMessageEvent)],
            ["missed"],
        )

    async def test_resync_emits_new_chat_and_unseen_message(self):
        chat = ChatSchema.model_validate(
            {"id": "c1", "type": "PM", "lastMessage": _recent_message()}
        )
        chats = _RawChats(page=_chat_page(chat))
        listener = EventListener(_Client(chats=chats))

        events = await listener._resync()

        self.assertIsInstance(events[0], ChatInitializedEvent)
        self.assertIsInstance(events[-1], NewMessageEvent)
        self.assertEqual(events[-1].message.id, "m1")
        self.assertIn("c1", listener.known_chat_ids)

    async def test_resync_skips_old_messages(self):
        old = _recent_message()
        old["createdAt"] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        chat = ChatSchema.model_validate({"id": "c1", "type": "PM", "lastMessage": old})
        listener = EventListener(_Client(chats=_RawChats(page=_chat_page(chat))))

        events = await listener._resync()

        self.assertEqual([event for event in events if isinstance(event, NewMessageEvent)], [])


class ReviewsOnlyModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_baseline_deals_are_not_treated_as_new(self):
        raw_deals = _RawDeals(
            pages=[SimpleNamespace(deals=[SimpleNamespace(id="d1"), SimpleNamespace(id="d2")])]
        )
        listener = EventListener(_Client(deals=raw_deals))

        await listener._refresh_known_deals()

        self.assertEqual(listener.known_deal_ids, {"d1", "d2"})
        self.assertEqual(listener.review_deal_ids, [])

    async def test_new_deal_is_polled_for_review_without_messages(self):
        raw_deals = _RawDeals(
            pages=[
                SimpleNamespace(deals=[SimpleNamespace(id="d1")]),
                SimpleNamespace(deals=[SimpleNamespace(id="d1"), SimpleNamespace(id="d2")]),
            ],
            deals={
                "d2": ItemDeal.model_validate(
                    {
                        "id": "d2",
                        "status": "CONFIRMED",
                        "direction": "IN",
                        "testimonial": {"id": "r1", "status": "APPROVED", "rating": 5},
                        "chat": {"id": "c1", "type": "PM"},
                    }
                )
            },
        )
        listener = EventListener(_Client(deals=raw_deals))
        listener.review_delay = 0

        await listener._refresh_known_deals()
        await listener._refresh_known_deals()
        events = await listener.poll_reviews_once()

        self.assertEqual(listener.review_deal_ids, [])
        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], NewReviewEvent)
        self.assertEqual(events[0].deal.id, "d2")
        self.assertEqual(events[0].chat.id, "c1")

    async def test_review_stays_queued_until_chat_is_available(self):
        payload = {
            "id": "d1",
            "status": "CONFIRMED",
            "direction": "IN",
            "testimonial": {"id": "r1", "status": "APPROVED", "rating": 5},
        }
        raw_deals = _RawDeals(deals={"d1": ItemDeal.model_validate(payload)})
        listener = EventListener(_Client(deals=raw_deals), review_delay=0)
        listener.review_deal_ids.append("d1")

        self.assertEqual(await listener.poll_reviews_once(), [])
        self.assertEqual(listener.review_deal_ids, ["d1"])

        raw_deals.deals["d1"] = ItemDeal.model_validate(
            payload | {"chat": {"id": "c1", "type": "PM"}}
        )
        listener.review_checks["d1"]["last"] = 0.0
        events = await listener.poll_reviews_once()

        self.assertEqual(len(events), 1)
        self.assertIsInstance(events[0], NewReviewEvent)
        self.assertEqual(listener.review_deal_ids, [])
