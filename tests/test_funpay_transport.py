import asyncio
import unittest
from unittest import mock

from aiosellers.funpay import FunPayClientConfig
from aiosellers.funpay.exceptions import RequestFailedError
from aiosellers.funpay.transport.tls import FunPayTransport

_OK = 200


class _Response:
    def __init__(self, status_code=_OK, text="{}", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.cookies = {}
        self.url = "https://funpay.com/"
        self.history = []


class _FakeTLSClient:
    last = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.get_calls = 0
        self.post_calls = 0
        self.responses: list[_Response] = []
        self.cookies = {}
        self.closed = False
        _FakeTLSClient.last = self

    async def get(self, url, headers=None):
        self.get_calls += 1
        return self.responses.pop(0)

    async def post(self, url, headers=None, **kwargs):
        self.post_calls += 1
        return self.responses.pop(0)

    async def aclose(self):
        self.closed = True


class TransportTestBase(unittest.IsolatedAsyncioTestCase):
    def make_transport(self, **overrides) -> FunPayTransport:
        patcher = mock.patch("tls_requests.AsyncClient", _FakeTLSClient)
        patcher.start()
        self.addCleanup(patcher.stop)
        config = FunPayClientConfig(golden_key="key", **overrides)
        return FunPayTransport(config)

    def fake_sleep(self):
        sleeper = mock.AsyncMock()
        patcher = mock.patch("aiosellers.funpay.transport.tls.asyncio.sleep", sleeper)
        patcher.start()
        self.addCleanup(patcher.stop)
        return sleeper


class RetryTests(TransportTestBase):
    async def test_get_retries_5xx_with_backoff(self):
        sleep = self.fake_sleep()
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [_Response(503), _Response(200)]

        response = await transport.request("GET", "/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake.get_calls, 2)
        sleep.assert_awaited_once()
        await transport.close()

    async def test_get_retries_network_errors(self):
        sleep = self.fake_sleep()
        transport = self.make_transport()
        fake = transport._client
        calls = []

        async def get(url, headers=None):
            calls.append(url)
            if len(calls) < 3:
                raise ConnectionResetError("reset")
            return _Response()

        fake.get = get  # type: ignore[method-assign]

        response = await transport.request("GET", "/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleep.await_count, 2)
        await transport.close()

    async def test_get_does_not_retry_4xx(self):
        sleep = self.fake_sleep()
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [_Response(404)]

        with self.assertRaises(RequestFailedError):
            await transport.request("GET", "/")

        self.assertEqual(fake.get_calls, 1)
        sleep.assert_not_awaited()
        await transport.close()

    async def test_post_is_not_retried(self):
        sleep = self.fake_sleep()
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [_Response(503), _Response(200)]

        with self.assertRaises(RequestFailedError):
            await transport.request("POST", "runner/", data={"a": "b"})

        self.assertEqual(fake.post_calls, 1)
        sleep.assert_not_awaited()
        await transport.close()


class ConcurrencyTests(TransportTestBase):
    async def test_requests_are_bounded_by_the_limiter(self):
        transport = self.make_transport(max_concurrent_requests=2)
        fake = transport._client
        gate = asyncio.Event()
        active = 0
        peak = 0

        async def get(url, headers=None):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await gate.wait()
            active -= 1
            return _Response()

        fake.get = get  # type: ignore[method-assign]

        tasks = [asyncio.create_task(transport.request("GET", f"/{index}")) for index in range(5)]
        await asyncio.sleep(0.05)
        self.assertEqual(len([task for task in tasks if not task.done()]), 5)
        self.assertEqual(peak, 2)

        gate.set()
        await asyncio.gather(*tasks)
        self.assertEqual(peak, 2)
        await transport.close()
