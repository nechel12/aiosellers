import socket
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from aiosellers.playerok.core import utils
from aiosellers.playerok.core.constants import BASE_HEADERS, EXAMPLE_USER_AGENTS
from aiosellers.playerok.core.exceptions import GraphQLError, PersistedQueryExpired
from aiosellers.playerok.core.utils import _raise_on_gql_errors, prepare_image_file
from aiosellers.playerok.entities.chat import Chat
from aiosellers.playerok.listener import _DRIFT_WARNED, parse_chat, parse_chat_message
from aiosellers.playerok.schemas.basic import _WARNED_MODELS
from aiosellers.playerok.schemas.chats import Moderator


class GraphQLErrorTests(unittest.TestCase):
    def test_persisted_query_not_found_is_explicit(self):
        payload = {
            "errors": [
                {
                    "message": "PersistedQueryNotFound",
                    "extensions": {"code": "PERSISTED_QUERY_NOT_FOUND"},
                }
            ]
        }
        with self.assertRaisesRegex(PersistedQueryExpired, "frontend contract"):
            _raise_on_gql_errors(payload)

    def test_persisted_query_code_without_marker_is_still_detected(self):
        payload = {
            "errors": [
                {
                    "message": "unknown query",
                    "extensions": {"code": "PERSISTED_QUERY_HASH_MISMATCH"},
                }
            ]
        }
        with self.assertRaises(PersistedQueryExpired):
            _raise_on_gql_errors(payload)

    def test_regular_errors_stay_graphql_errors(self):
        payload = {"errors": [{"message": "not authorized"}]}
        with self.assertRaises(GraphQLError) as ctx:
            _raise_on_gql_errors(payload)
        self.assertNotIsInstance(ctx.exception, PersistedQueryExpired)

    def test_no_errors_is_a_noop(self):
        _raise_on_gql_errors({"data": {}})
        _raise_on_gql_errors({})


class _ImageResponse:
    def __init__(self, status_code=200, content=b"image", headers=None):
        self.status_code = status_code
        self.content = content
        self.text = ""
        self.headers = headers or {}


class _ImageClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def _resolved_address(address):
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    return (family, socket.SOCK_STREAM, 6, "", (address, 443))


class ImageDownloadTests(unittest.IsolatedAsyncioTestCase):
    def mock_client(self, responses):
        client = _ImageClient(responses)
        patcher = mock.patch("tls_requests.AsyncClient", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return client

    async def test_remote_image_validates_redirects_and_disables_auto_redirects(self):
        client = self.mock_client(
            [
                _ImageResponse(302, headers={"Location": "/next.png"}),
                _ImageResponse(content=b"ok"),
            ]
        )
        with mock.patch.object(
            utils.socket, "getaddrinfo", return_value=[_resolved_address("93.184.216.34")]
        ) as resolve:
            file_obj, should_close = await prepare_image_file("https://example.com/image.png")

        self.assertEqual(file_obj.getvalue(), b"ok")
        self.assertFalse(should_close)
        self.assertEqual(resolve.call_count, 2)
        self.assertEqual(
            [call[0] for call in client.calls],
            ["https://example.com/image.png", "https://example.com/next.png"],
        )
        for _, kwargs in client.calls:
            self.assertFalse(kwargs["follow_redirects"])

    async def test_remote_image_rejects_credentials_and_non_http_urls(self):
        with self.assertRaises(ValueError):
            await prepare_image_file("https://user:pass@example.com/image.png")
        with self.assertRaises(ValueError):
            await prepare_image_file("file:///etc/passwd")

    async def test_remote_image_rejects_non_public_ipv4_and_ipv6(self):
        addresses = (
            "127.0.0.1",
            "10.0.0.1",
            "169.254.1.1",
            "224.0.0.1",
            "240.0.0.1",
            "::1",
            "fc00::1",
            "fe80::1",
            "ff02::1",
        )
        for address in addresses:
            with self.subTest(address=address):
                with (
                    mock.patch("tls_requests.AsyncClient") as client_class,
                    mock.patch.object(
                        utils.socket,
                        "getaddrinfo",
                        return_value=[_resolved_address(address)],
                    ),
                ):
                    with self.assertRaises(PermissionError):
                        await prepare_image_file("https://example.com/image.png")
                    client_class.assert_not_called()

    async def test_remote_image_rejects_redirect_to_private_address(self):
        client = self.mock_client(
            [_ImageResponse(302, headers={"Location": "https://internal.example/image.png"})]
        )
        with mock.patch.object(
            utils.socket,
            "getaddrinfo",
            side_effect=[
                [_resolved_address("93.184.216.34")],
                [_resolved_address("192.168.1.2")],
            ],
        ):
            with self.assertRaises(PermissionError):
                await prepare_image_file("https://example.com/image.png")
        self.assertEqual(len(client.calls), 1)

    async def test_remote_image_enforces_size_limit(self):
        self.mock_client([_ImageResponse(content=b"12345")])
        with (
            mock.patch.object(utils, "MAX_IMAGE_DOWNLOAD_BYTES", 4),
            mock.patch.object(
                utils.socket,
                "getaddrinfo",
                return_value=[_resolved_address("93.184.216.34")],
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "download limit"):
                await prepare_image_file("https://example.com/image.png")

    async def test_remote_image_limits_redirects(self):
        client = self.mock_client(
            [
                _ImageResponse(302, headers={"Location": f"/{index}.png"})
                for index in range(utils.IMAGE_REDIRECT_LIMIT + 1)
            ]
        )
        with mock.patch.object(
            utils.socket, "getaddrinfo", return_value=[_resolved_address("93.184.216.34")]
        ):
            with self.assertRaisesRegex(RuntimeError, "redirects"):
                await prepare_image_file("https://example.com/image.png")
        self.assertEqual(len(client.calls), utils.IMAGE_REDIRECT_LIMIT + 1)

    async def test_local_image_inputs_keep_their_behavior(self):
        source = BytesIO(b"source")
        file_obj, should_close = await prepare_image_file(source)
        self.assertIs(file_obj, source)
        self.assertFalse(should_close)

        file_obj, should_close = await prepare_image_file(b"bytes")
        self.assertEqual(file_obj.getvalue(), b"bytes")
        self.assertFalse(should_close)

        with mock.patch("builtins.open", mock.mock_open(read_data=b"local")) as open_file:
            file_obj, should_close = await prepare_image_file(Path("local.png"))
        self.assertTrue(should_close)
        open_file.assert_called_once_with("local.png", "rb")


class SchemaDriftTests(unittest.TestCase):
    def setUp(self):
        _DRIFT_WARNED.clear()

    def test_message_drift_warns_once_and_returns_partial_data(self):
        payload = {
            "id": "m1",
            "text": "hi",
            "createdAt": "2026-01-01T00:00:00Z",
            "isRead": True,
            "user": "not-an-object",
        }
        with self.assertLogs("aiosellers.playerok.listener", level="WARNING") as logs:
            first = parse_chat_message(payload)
            second = parse_chat_message(payload)

        self.assertEqual(first.id, "m1")
        self.assertEqual(first.text, "hi")
        self.assertIsNone(second.user)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("chat message", logs.records[0].getMessage())

    def test_chat_drift_is_reported(self):
        payload = {"id": "c1", "lastMessage": "not-an-object"}
        with self.assertLogs("aiosellers.playerok.listener", level="WARNING") as logs:
            chat = parse_chat(payload)

        self.assertEqual(chat.id, "c1")
        self.assertIsNone(chat.last_message)
        self.assertIn("chat", logs.records[0].getMessage())


class UserAgentTests(unittest.TestCase):
    def test_example_user_agents_match_client_hints(self):
        major = BASE_HEADERS["sec-ch-ua"].split("v=")[1].split('"')[1]
        self.assertTrue(EXAMPLE_USER_AGENTS)
        for agent in EXAMPLE_USER_AGENTS:
            self.assertIn(f"Chrome/{major}.", agent)
            self.assertIn("Macintosh", agent)


class ChatEntityTests(unittest.IsolatedAsyncioTestCase):
    async def test_iter_messages_returns_an_async_iterator(self):
        class Messages:
            async def iter(self, chat_id):
                yield f"message-for-{chat_id}"

        class Chats:
            messages = Messages()

        class Client:
            chats = Chats()

        chat = Chat(id="c1")
        chat._client = Client()

        messages = [message async for message in chat.iter_messages()]

        self.assertEqual(messages, ["message-for-c1"])


class AccountSchemaTests(unittest.TestCase):
    def test_null_last_item_created_at_is_accepted(self):
        from aiosellers.playerok.schemas import Account

        account = Account.model_validate(
            {
                "id": "1",
                "username": "seller",
                "email": "seller@example.com",
                "role": "USER",
                "hasFrozenBalance": False,
                "supportChatId": "support",
                "systemChatId": "system",
                "unreadChatsCounter": 0,
                "isBlocked": False,
                "createdAt": "2026-01-01T00:00:00Z",
                "lastItemCreatedAt": None,
                "hasConfirmedPhoneNumber": False,
                "canPublishItems": True,
                "isFundsProtectionActive": False,
            }
        )

        self.assertIsNone(account.last_item_created_at)


class UnimplementedModelTests(unittest.TestCase):
    def setUp(self):
        _WARNED_MODELS.clear()

    def test_unimplemented_model_warns_once(self):
        with self.assertLogs("aiosellers.playerok.schemas.basic", level="WARNING") as logs:
            Moderator(id="1")
            Moderator(id="2")

        self.assertEqual(len(logs.records), 1)
