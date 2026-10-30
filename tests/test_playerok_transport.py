import unittest
from unittest import mock

from aiosellers.playerok.core.config import PlayerokConfig
from aiosellers.playerok.core.exceptions import (
    RateLimitedError,
    RequestFailedError,
)
from aiosellers.playerok.transport import tls
from aiosellers.playerok.transport.tls import PlayerokTransport


class _Response:
    def __init__(self, status_code=200, text="", content=b"payload", headers=None):
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = headers or {}


class _FakeClient:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []
        self.closed = False

    async def get(self, url=None, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self._next()

    async def post(self, url=None, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self._next()

    def _next(self):
        if not self.responses:
            return _Response()
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self):
        self.closed = True


async def _no_sleep(_delay):
    return None


class TransportTestBase(unittest.IsolatedAsyncioTestCase):
    def make_transport(self, session_responses=None, download_responses=None):
        self.session = _FakeClient(session_responses)
        self.download = _FakeClient(download_responses)
        self.created = []

        def factory(**kwargs):
            self.created.append(kwargs)
            return self.session if len(self.created) == 1 else self.download

        patcher = mock.patch("tls_requests.AsyncClient", side_effect=factory)
        patcher.start()
        self.addCleanup(patcher.stop)
        transport = PlayerokTransport(
            access_token="token",
            config=PlayerokConfig(base_url="https://playerok.com/"),
        )
        return transport


class RequestTests(TransportTestBase):
    async def test_get_retries_on_server_error(self):
        transport = self.make_transport([_Response(503), _Response(200)])
        with mock.patch.object(tls.asyncio, "sleep", _no_sleep):
            response = await transport.request("get", "/graphql", {"query": "x"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.session.calls), 2)

    async def test_get_honours_retry_after_on_429(self):
        transport = self.make_transport(
            [_Response(429, headers={"retry-after": "0.25"}), _Response(200)]
        )
        delays = []

        async def fake_sleep(delay):
            delays.append(delay)

        with mock.patch.object(tls.asyncio, "sleep", fake_sleep):
            response = await transport.request("get", "/graphql")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(delays, [0.25])

    async def test_get_raises_after_too_many_rate_limits(self):
        transport = self.make_transport([_Response(429), _Response(429), _Response(429)])
        with mock.patch.object(tls.asyncio, "sleep", _no_sleep), self.assertRaises(
            RateLimitedError
        ):
            await transport.request("get", "/graphql")
        self.assertEqual(len(self.session.calls), 3)

    async def test_post_is_not_retried(self):
        transport = self.make_transport([_Response(503)])
        with self.assertRaises(RequestFailedError):
            await transport.request("post", "/graphql", {"query": "x"})
        self.assertEqual(len(self.session.calls), 1)

        transport = self.make_transport([_Response(429, headers={"retry-after": "5"})])
        with self.assertRaises(RateLimitedError):
            await transport.request("post", "/graphql", {"query": "x"})
        self.assertEqual(len(self.session.calls), 1)

    async def test_client_error_is_raised_immediately(self):
        transport = self.make_transport([_Response(403)])
        with self.assertRaises(RequestFailedError):
            await transport.request("get", "/graphql")
        self.assertEqual(len(self.session.calls), 1)

    async def test_get_retries_network_errors(self):
        transport = self.make_transport([ConnectionError("boom"), _Response(200)])
        with mock.patch.object(tls.asyncio, "sleep", _no_sleep):
            response = await transport.request("get", "/graphql")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.session.calls), 2)


class DownloadTests(TransportTestBase):
    async def test_download_uses_unauthenticated_client(self):
        transport = self.make_transport(download_responses=[_Response(200, content=b"img")])
        data = await transport.download("https://playerok.com/files/pic.png")

        self.assertEqual(data, b"img")
        self.assertEqual(self.session.calls, [])
        self.assertEqual(len(self.download.calls), 1)
        self.assertNotIn("cookies", self.created[1])

    async def test_download_rejects_untrusted_host(self):
        transport = self.make_transport(download_responses=[_Response(200)])
        with self.assertRaises(PermissionError):
            await transport.download("https://evil.example.com/pic.png")
        self.assertEqual(self.download.calls, [])
        self.assertEqual(self.session.calls, [])

    async def test_download_rejects_credentials_in_url(self):
        transport = self.make_transport(download_responses=[_Response(200)])
        with self.assertRaises(ValueError):
            await transport.download("https://user:pass@playerok.com/pic.png")
        self.assertEqual(self.download.calls, [])

    async def test_download_resolves_relative_url(self):
        transport = self.make_transport(download_responses=[_Response(200, content=b"x")])
        await transport.download("/files/pic.png")
        self.assertEqual(self.download.calls[0][1], "https://playerok.com/files/pic.png")

    async def test_download_allows_playerok_subdomains(self):
        transport = self.make_transport(download_responses=[_Response(200, content=b"x")])
        await transport.download("https://cdn.playerok.com/pic.png")
        self.assertEqual(self.download.calls[0][1], "https://cdn.playerok.com/pic.png")

    async def test_download_retries_server_errors(self):
        transport = self.make_transport(
            download_responses=[_Response(502), _Response(200, content=b"ok")]
        )
        with mock.patch.object(tls.asyncio, "sleep", _no_sleep):
            data = await transport.download("https://playerok.com/pic.png")
        self.assertEqual(data, b"ok")
        self.assertEqual(len(self.download.calls), 2)

    async def test_download_raises_rate_limited_after_retries(self):
        transport = self.make_transport(
            download_responses=[
                _Response(429, headers={"retry-after": "0"}),
                _Response(429, headers={"retry-after": "0"}),
                _Response(429, headers={"retry-after": "0"}),
            ]
        )
        with mock.patch.object(tls.asyncio, "sleep", _no_sleep), self.assertRaises(
            RateLimitedError
        ):
            await transport.download("https://playerok.com/pic.png")
        self.assertEqual(len(self.download.calls), 3)

    async def test_download_fails_fast_on_client_error(self):
        transport = self.make_transport(download_responses=[_Response(404)])
        with self.assertRaises(RequestFailedError):
            await transport.download("https://playerok.com/pic.png")
        self.assertEqual(len(self.download.calls), 1)

    async def test_close_closes_both_clients(self):
        transport = self.make_transport(download_responses=[_Response(200)])
        await transport.download("https://playerok.com/pic.png")
        await transport.close()
        self.assertTrue(self.session.closed)
        self.assertTrue(self.download.closed)
