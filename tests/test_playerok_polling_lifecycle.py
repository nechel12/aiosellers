import asyncio
import unittest
from unittest import mock

from aiosellers.playerok import Playerok


class PollingLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def make_client(self):
        client = Playerok("token")
        client._transport = object()
        client.close = mock.AsyncMock()  # type: ignore[method-assign]
        return client

    async def test_unexpected_feed_error_keeps_session_open(self):
        client = self.make_client()

        async def boom(**kwargs):
            if False:
                yield
            raise RuntimeError("feed died")

        client.listen = boom  # type: ignore[method-assign]

        with self.assertRaisesRegex(RuntimeError, "feed died"):
            await client.start_polling()

        client.close.assert_not_awaited()
        self.assertIsNotNone(client._transport)
        self.assertIsNone(client._polling_task)

    async def test_explicit_stop_closes_session(self):
        client = self.make_client()
        started = asyncio.Event()

        async def wait_forever(**kwargs):
            started.set()
            await asyncio.sleep(3600)
            yield

        client.listen = wait_forever  # type: ignore[method-assign]

        task = asyncio.create_task(client.start_polling())
        await started.wait()
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task

        client.close.assert_awaited_once()
        self.assertIsNone(client._polling_task)
