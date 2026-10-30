import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from aiosellers import FunPay, FunPayClientConfig, Playerok, PlayerokClientConfig


class _PollingClient:
    """Shared helpers for blocking polling loops used by both clients."""

    def install(self, client):
        client.started_event = asyncio.Event()
        client.closed_event = asyncio.Event()

        async def fake_start():
            return None

        async def fake_listen(**options):
            client.started_event.set()
            try:
                await asyncio.sleep(3600)
                yield
            finally:
                client.closed_event.set()

        client.start = fake_start  # type: ignore[method-assign]
        client.listen = fake_listen  # type: ignore[method-assign]
        client.close = mock.AsyncMock()  # type: ignore[method-assign]
        return client


class PlayerokLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_is_atomic_and_can_be_retried(self):
        with (
            mock.patch("aiosellers.playerok.playerok.PlayerokTransport") as transport_cls,
            mock.patch("aiosellers.playerok.playerok.RawAPI") as raw_cls,
        ):
            transport = transport_cls.return_value
            transport.close = mock.AsyncMock()
            raw = raw_cls.return_value
            raw.account.get_me = mock.AsyncMock(
                side_effect=[RuntimeError("boom"), SimpleNamespace(id="me-1")]
            )
            client = Playerok(PlayerokClientConfig(access_token="token"))

            with self.assertRaises(RuntimeError):
                await client.start()

            transport.close.assert_awaited_once()
            self.assertIsNone(client._transport)
            self.assertIsNone(client._raw)
            self.assertIsNone(client.me_id)

            await client.start()
            self.assertIs(client._transport, transport)
            self.assertEqual(client.me_id, "me-1")

    async def test_concurrent_starts_create_one_transport(self):
        with (
            mock.patch("aiosellers.playerok.playerok.PlayerokTransport") as transport_cls,
            mock.patch("aiosellers.playerok.playerok.RawAPI") as raw_cls,
        ):
            transport = transport_cls.return_value
            transport.close = mock.AsyncMock()
            get_me_started = asyncio.Event()
            finish_get_me = asyncio.Event()

            async def get_me():
                get_me_started.set()
                await finish_get_me.wait()
                return SimpleNamespace(id="me-1")

            raw_cls.return_value.account.get_me = get_me
            client = Playerok(PlayerokClientConfig(access_token="token"))
            first = asyncio.create_task(client.start())
            await asyncio.wait_for(get_me_started.wait(), 1)
            second = asyncio.create_task(client.start())
            finish_get_me.set()
            await asyncio.gather(first, second)

            transport_cls.assert_called_once()
            transport.close.assert_not_awaited()
            self.assertIs(client._transport, transport)
            self.assertEqual(client.me_id, "me-1")

    async def test_close_waits_for_inflight_start(self):
        with (
            mock.patch("aiosellers.playerok.playerok.PlayerokTransport") as transport_cls,
            mock.patch("aiosellers.playerok.playerok.RawAPI") as raw_cls,
        ):
            transport = transport_cls.return_value
            transport.close = mock.AsyncMock()
            get_me_started = asyncio.Event()
            finish_get_me = asyncio.Event()

            async def get_me():
                get_me_started.set()
                await finish_get_me.wait()
                return SimpleNamespace(id="me-1")

            raw_cls.return_value.account.get_me = get_me
            client = Playerok(PlayerokClientConfig(access_token="token"))
            starting = asyncio.create_task(client.start())
            await asyncio.wait_for(get_me_started.wait(), 1)
            closing = asyncio.create_task(client.close())
            finish_get_me.set()
            await asyncio.gather(starting, closing)

            transport.close.assert_awaited_once()
            self.assertIsNone(client._transport)
            self.assertIsNone(client._raw)
            self.assertIsNone(client.me_id)

    def test_access_token_is_hidden_from_config_repr(self):
        config = PlayerokClientConfig(access_token="secret-token")

        self.assertNotIn("secret-token", repr(config))

    async def test_stop_cancels_polling_and_closes(self):
        client = _PollingClient().install(Playerok(PlayerokClientConfig(access_token="token")))
        task = asyncio.create_task(client.start_polling())
        await asyncio.wait_for(client.started_event.wait(), 1)

        client.stop()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)

        client.close.assert_awaited_once()
        self.assertTrue(client.closed_event.is_set())
        self.assertIsNone(client._polling_task)

    def test_stop_without_polling_is_noop(self):
        client = Playerok(PlayerokClientConfig(access_token="token"))
        client.stop()
        self.assertIsNone(client._polling_task)


class FunPayLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_cancels_polling_and_closes(self):
        client = _PollingClient().install(FunPay(FunPayClientConfig(golden_key="key")))
        task = asyncio.create_task(client.start_polling())
        await asyncio.wait_for(client.started_event.wait(), 1)

        client.stop()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)

        client.close.assert_awaited_once()
        self.assertTrue(client.closed_event.is_set())
        self.assertIsNone(client._polling_task)

    def test_stop_without_polling_is_noop(self):
        client = FunPay(FunPayClientConfig(golden_key="key"))
        client.stop()
        self.assertIsNone(client._polling_task)
