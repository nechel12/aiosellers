import time
import unittest
from types import SimpleNamespace
from unittest import mock

from aiosellers.funpay import FunPay, FunPayClientConfig
from aiosellers.funpay.exceptions import RateLimitedError
from aiosellers.funpay.raw.base import RawBase
from aiosellers.funpay.transport.tls import FunPayTransport

BOOKMARK = """
<a class="contact-item" data-id="3" data-node-msg="10" data-user-msg="9">
  <div class="media-user-name">Ann</div>
  <div class="contact-item-message">{text}</div>
</a>
"""


class _RunnerRaw:
    def __init__(self, html):
        self.html = html
        self.account = self

    async def runner(self, objects):
        assert objects
        return {"objects": [{"type": "chat_bookmarks", "data": {"html": self.html}}]}


class ChatIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_keeps_existing_chat_objects(self):
        client = FunPay(FunPayClientConfig(golden_key="key"))
        client._account_id = 5
        client._raw = _RunnerRaw(BOOKMARK.format(text="hello"))

        first = await client.chats.list()
        client._raw.html = BOOKMARK.format(text="updated")
        second = await client.chats.list()

        self.assertIs(first[0], second[0])
        self.assertEqual(second[0].last_message_text, "updated")
        self.assertIs(client.cached("chats", 3), first[0])


class RawRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limit_retries_with_backoff(self):
        transport = SimpleNamespace(rate_limited_until=0.0)
        raw = RawBase(transport)
        attempts = []

        async def factory():
            attempts.append(len(attempts))
            if len(attempts) < 3:
                raise RateLimitedError("429")
            return "ok"

        delays = []

        async def fake_sleep(delay):
            delays.append(delay)

        with mock.patch("aiosellers.funpay.raw.base.asyncio.sleep", fake_sleep):
            result = await raw._retry(factory)

        self.assertEqual(result, "ok")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len(delays), 2)

    async def test_rate_limit_gives_up_after_attempts(self):
        transport = SimpleNamespace(rate_limited_until=0.0)
        raw = RawBase(transport)
        attempts = []

        async def factory():
            attempts.append(1)
            raise RateLimitedError("429")

        async def fake_sleep(_delay):
            return None

        with mock.patch("aiosellers.funpay.raw.base.asyncio.sleep", fake_sleep):
            with self.assertRaises(RateLimitedError):
                await raw._retry(factory)
        self.assertEqual(len(attempts), 3)


class RetryAfterTests(unittest.TestCase):
    def test_rate_limit_honours_retry_after_header(self):
        transport = object.__new__(FunPayTransport)
        transport.rate_limited_until = 0.0
        response = SimpleNamespace(
            status_code=429,
            text="",
            headers={"retry-after": "5"},
        )

        before = time.monotonic()
        with self.assertRaises(RateLimitedError):
            transport._raise_for_status(response, raise_not_200=True)
        self.assertGreaterEqual(transport.rate_limited_until - before, 4.5)

    def test_rate_limit_falls_back_to_a_minute(self):
        transport = object.__new__(FunPayTransport)
        transport.rate_limited_until = 0.0
        response = SimpleNamespace(status_code=429, text="", headers={})

        before = time.monotonic()
        with self.assertRaises(RateLimitedError):
            transport._raise_for_status(response, raise_not_200=True)
        self.assertGreaterEqual(transport.rate_limited_until - before, 59.0)
