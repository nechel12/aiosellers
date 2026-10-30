import asyncio
import unittest
from types import SimpleNamespace

from aiosellers import (
    Capability,
    EventKind,
    FunPay,
    FunPayClientConfig,
    GGsel,
    GGselClientConfig,
    Platform,
    Playerok,
    PlayerokClientConfig,
    SellerClient,
    SellerHub,
)
from aiosellers.core import capabilities_for, event_kind
from aiosellers.funpay.schemas import EventTypes as FunPayEvents
from aiosellers.ggsel.schemas import EventTypes as GGselEvents
from aiosellers.playerok.schemas import EventTypes as PlayerokEvents


def _event(kind):
    return SimpleNamespace(type=kind, client=None)


class _FakeClient:
    def __init__(self, events=(), *, fail_start=False, fail_listen=False, hold=False):
        self.events = list(events)
        self.fail_start = fail_start
        self.fail_listen = fail_listen
        self.hold = hold
        self.started = False
        self.closed = False
        self.listen_cancelled = False
        self.options: dict = {}

    async def start(self):
        if self.fail_start:
            raise RuntimeError("start failed")
        self.started = True

    async def close(self):
        self.closed = True

    async def listen(self, **options):
        self.options = options
        try:
            if self.fail_listen:
                raise RuntimeError("listen failed")
            for event in self.events:
                yield event
            if self.hold:
                await asyncio.sleep(3600)
        finally:
            self.listen_cancelled = True


class CapabilityTests(unittest.TestCase):
    def test_capability_matrix_matches_platform_size(self):
        funpay = capabilities_for(Platform.FUNPAY)
        playerok = capabilities_for("playerok")
        ggsel = capabilities_for(Platform.GGSEL)

        self.assertIn(Capability.ORDERS, funpay)
        self.assertIn(Capability.PURCHASES, funpay)
        self.assertNotIn(Capability.WEBSOCKET, funpay)
        self.assertIn(Capability.DEALS, playerok)
        self.assertIn(Capability.ITEM_PRIORITY, playerok)
        self.assertIn(Capability.WEBSOCKET, playerok)
        self.assertNotIn(Capability.ORDERS, playerok)
        self.assertIn(Capability.ORDERS, ggsel)
        self.assertIn(Capability.MESSAGES, ggsel)
        self.assertIn(Capability.REVIEWS, ggsel)
        self.assertNotIn(Capability.WEBSOCKET, ggsel)

    def test_event_kind_maps_both_platforms_and_unknown_names(self):
        self.assertIs(
            event_kind(Platform.FUNPAY, _event(FunPayEvents.LAST_CHAT_MESSAGE_CHANGED)),
            EventKind.MESSAGE,
        )
        self.assertIs(
            event_kind(Platform.FUNPAY, _event(FunPayEvents.ORDERS_LIST_CHANGED)),
            EventKind.LIST,
        )
        self.assertIs(
            event_kind(Platform.PLAYEROK, _event(PlayerokEvents.ITEM_SENT)), EventKind.DEAL
        )
        self.assertIs(
            event_kind(Platform.PLAYEROK, _event(PlayerokEvents.NEW_REVIEW)), EventKind.REVIEW
        )
        self.assertIs(event_kind(Platform.GGSEL, _event(GGselEvents.NEW_SALE)), EventKind.ORDER)
        self.assertIs(event_kind(Platform.GGSEL, _event(GGselEvents.NEW_REVIEW)), EventKind.REVIEW)
        self.assertIs(
            event_kind(Platform.GGSEL, _event(GGselEvents.INITIAL_CHAT)), EventKind.INITIAL
        )
        future = SimpleNamespace(name="NEW_REVIEW_V2")
        self.assertIs(event_kind(Platform.PLAYEROK, _event(future)), EventKind.REVIEW)
        mystery = SimpleNamespace(name="SOMETHING_ELSE")
        self.assertIs(event_kind(Platform.PLAYEROK, _event(mystery)), EventKind.OTHER)


class HubTests(unittest.IsolatedAsyncioTestCase):
    def test_both_clients_satisfy_the_protocol(self):
        self.assertIsInstance(FunPay(FunPayClientConfig(golden_key="key")), SellerClient)
        self.assertIsInstance(Playerok(PlayerokClientConfig(access_token="token")), SellerClient)
        self.assertIsInstance(GGsel(GGselClientConfig(api_key="key", seller_id=42)), SellerClient)

    def test_session_ids_and_duplicates(self):
        hub = SellerHub()
        first = hub.add(_FakeClient(), platform=Platform.FUNPAY)
        second = hub.add(_FakeClient(), platform=Platform.PLAYEROK)
        third = hub.add(_FakeClient(), platform="funpay")

        self.assertEqual(first.id, "funpay-1")
        self.assertEqual(second.id, "playerok-1")
        self.assertEqual(third.id, "funpay-2")
        self.assertIn(Capability.REVIEWS, first.capabilities)
        with self.assertRaises(ValueError):
            hub.add(_FakeClient(), platform="funpay", session_id="funpay-1")
        with self.assertRaises(KeyError):
            hub.get("missing")

    async def test_start_rolls_back_sessions_that_already_started(self):
        hub = SellerHub()
        good = _FakeClient()
        bad = _FakeClient(fail_start=True)
        hub.add(good, platform="funpay")
        hub.add(bad, platform="playerok")

        with self.assertRaises(RuntimeError):
            await hub.start()

        self.assertTrue(good.started)
        self.assertTrue(good.closed)
        self.assertFalse(bad.started)

    async def test_stream_tags_events_and_honours_listen_options(self):
        funpay = _FakeClient([_event(FunPayEvents.NEW_MESSAGE), _event(FunPayEvents.NEW_ORDER)])
        playerok = _FakeClient([_event(PlayerokEvents.NEW_REVIEW)])
        hub = SellerHub()
        hub.add(funpay, platform="funpay", session_id="shop")
        hub.add(playerok, platform="playerok", listen_options={"messages": False})
        await hub.start()

        merged = [item async for item in hub.stream()]

        self.assertEqual(
            {(item.session_id, item.kind) for item in merged},
            {
                ("shop", EventKind.MESSAGE),
                ("shop", EventKind.ORDER),
                ("playerok-1", EventKind.REVIEW),
            },
        )
        self.assertTrue(all(item.event.client is None for item in merged))
        self.assertEqual(playerok.options, {"messages": False})
        self.assertTrue(funpay.started and playerok.started)
        self.assertFalse(funpay.closed or playerok.closed)

        await hub.close()
        self.assertTrue(funpay.closed and playerok.closed)

    async def test_failing_listener_does_not_hide_other_sessions(self):
        broken = _FakeClient(fail_listen=True)
        working = _FakeClient([_event(FunPayEvents.NEW_MESSAGE)])
        hub = SellerHub()
        hub.add(broken, platform="playerok", session_id="broken")
        hub.add(working, platform="funpay", session_id="working")
        await hub.start()

        merged = [item async for item in hub.stream()]

        self.assertEqual([item.session_id for item in merged], ["working"])

    async def test_leaving_the_stream_cancels_listeners(self):
        client = _FakeClient([_event(FunPayEvents.NEW_MESSAGE)], hold=True)
        hub = SellerHub()
        hub.add(client, platform="funpay")
        await hub.start()

        stream = hub.stream()
        self.assertIsNotNone(await anext(stream))
        await stream.aclose()
        await asyncio.sleep(0)

        self.assertTrue(client.listen_cancelled)

    async def test_leaving_stream_with_full_buffer_does_not_deadlock(self):
        class FloodClient:
            async def start(self):
                pass

            async def close(self):
                pass

            async def listen(self, **options):
                index = 0
                while True:
                    index += 1
                    yield index

        hub = SellerHub(stream_buffer=1)
        hub.add(FloodClient(), platform="funpay", session_id="flood")
        await hub.start()

        stream = hub.stream()
        await anext(stream)
        await asyncio.sleep(0.05)
        await asyncio.wait_for(stream.aclose(), timeout=1)
        await hub.close()

    async def test_stream_requires_sessions(self):
        with self.assertRaises(RuntimeError):
            async for _ in SellerHub().stream():
                pass
