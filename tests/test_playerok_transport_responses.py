import unittest
from unittest import mock

from aiosellers.playerok.core.config import PlayerokConfig
from aiosellers.playerok.core.exceptions import GraphQLError, RequestFailedError
from aiosellers.playerok.transport.tls import PlayerokTransport


class _Response:
    def __init__(self, status_code=200, text="", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = False

    async def get(self, url=None, **kwargs):
        self.calls.append(("get", url, kwargs))
        return self.responses.pop(0)

    async def post(self, url=None, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self.responses.pop(0)

    async def aclose(self):
        self.closed = True


class ResponseParsingTests(unittest.IsolatedAsyncioTestCase):
    def make_transport(self, responses):
        client = _Client(responses)
        patcher = mock.patch("tls_requests.AsyncClient", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        transport = PlayerokTransport(
            access_token="token",
            config=PlayerokConfig(base_url="https://playerok.com/"),
        )
        return transport, client

    async def test_non_json_success_response_raises_graphql_error(self):
        transport, client = self.make_transport(
            [_Response(200, text="<!doctype html><html>error</html>")]
        )

        with self.assertRaisesRegex(GraphQLError, "non-JSON"):
            await transport.request("post", "graphql", {"query": "x"})

        self.assertEqual(len(client.calls), 1)
        await transport.close()

    async def test_json_success_response_is_returned(self):
        transport, _ = self.make_transport([_Response(200, text='{"data": {}}')])

        response = await transport.request("post", "graphql", {"query": "x"})

        self.assertEqual(response.status_code, 200)
        await transport.close()

    async def test_multipart_operations_without_files_are_sent_as_form_data(self):
        transport, client = self.make_transport([_Response(200, text='{"data": {}}')])

        await transport.request(
            "post",
            "graphql",
            {"operations": "{}", "map": "{}"},
        )

        kwargs = client.calls[0][2]
        self.assertIn("data", kwargs)
        self.assertEqual(kwargs["files"], {})
        self.assertNotIn("json", kwargs)
        await transport.close()

    async def test_error_message_includes_response_body(self):
        transport, _ = self.make_transport(
            [_Response(500, text="upstream exploded")]
        )

        with self.assertRaisesRegex(RequestFailedError, "upstream exploded"):
            await transport.request("post", "graphql", {"query": "x"})

        await transport.close()
