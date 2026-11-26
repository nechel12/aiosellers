import asyncio
import unittest
from unittest import mock

from aiosellers import AuthError, ConfigurationError, FunPay, GGsel, Playerok, SellerSession
from aiosellers.funpay.core.config import FunPayConfig
from aiosellers.funpay.exceptions import RequestFailedError as FunPayRequestFailedError
from aiosellers.funpay.exceptions import UnauthorizedError as FunPayUnauthorizedError
from aiosellers.ggsel.exceptions import GGselError
from aiosellers.ggsel.exceptions import UnauthorizedError as GGselUnauthorizedError
from aiosellers.ggsel.transport import GGselTransport
from aiosellers.playerok.core.exceptions import GraphQLError, Unauthorized
from aiosellers.playerok.core.utils import _raise_on_gql_errors
from aiosellers.playerok.transport import PlayerokTransport


class ErrorTests(unittest.TestCase):
    def test_platform_exceptions_keep_their_existing_bases(self):
        self.assertIsInstance(FunPayUnauthorizedError(), FunPayRequestFailedError)
        self.assertIsInstance(GGselUnauthorizedError(), GGselError)
        for error in (FunPayUnauthorizedError(), GGselUnauthorizedError(), Unauthorized()):
            self.assertIsInstance(error, AuthError)

    def test_missing_credentials_are_configuration_errors(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            for construct in (
                lambda: FunPayConfig.from_client(FunPay()._config),
                PlayerokTransport,
                GGselTransport,
                lambda: GGselTransport(api_key="fixture"),
                lambda: GGselTransport(api_key="fixture", seller_id=0),
            ):
                with self.subTest(construct=construct), self.assertRaises(ConfigurationError):
                    construct()

    def test_graphql_checks_auth_codes_without_turning_forbidden_into_auth(self):
        for code in ("UNAUTHENTICATED", "UNAUTHORIZED"):
            with self.subTest(code=code), self.assertRaises(AuthError):
                _raise_on_gql_errors(
                    {
                        "errors": [
                            {"message": "other"},
                            {"message": "fixture", "extensions": {"code": code}},
                        ]
                    }
                )
        with self.assertRaises(GraphQLError):
            _raise_on_gql_errors(
                {"errors": [{"message": "forbidden", "extensions": {"code": "FORBIDDEN"}}]}
            )


class SellerSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_sending_text_dispatches_without_retry_or_read_receipts(self):
        for client in (FunPay(), GGsel(), Playerok()):
            with self.subTest(platform=client.platform):
                method = "send" if isinstance(client, GGsel) else "send_message"
                with mock.patch.object(client.chats, method) as send:
                    await SellerSession(client).messages.send("chat", "hello")
                if isinstance(client, GGsel):
                    send.assert_awaited_once_with("chat", "hello")
                else:
                    send.assert_awaited_once_with("chat", text="hello")

    async def test_order_and_listing_reads_use_native_bounded_methods(self):
        client = GGsel()
        session = SellerSession(client)
        with (
            mock.patch.object(client.sales, "last", return_value=[1, 2]) as last,
            mock.patch.object(client.products, "my", return_value=[3]) as own,
        ):
            self.assertEqual(await session.orders.list(limit=1), [1])
            self.assertEqual(await session.listings.list(limit=2), [3])
        last.assert_awaited_once_with(top=1)
        own.assert_awaited_once_with(limit=2)

    async def test_limits_prevent_unbounded_calls_and_timeout_cancels_the_read(self):
        client = Playerok()
        with mock.patch.object(client.chats.messages, "list") as read:
            self.assertEqual(await SellerSession(client).messages.list("c", limit=0), [])
            with self.assertRaises(ValueError):
                await SellerSession(client).messages.list("c", limit=101)
            read.assert_not_called()

        async def block(*args, **kwargs):
            await asyncio.Future()

        with mock.patch.object(client.chats.messages, "list", side_effect=block):
            with self.assertRaises(TimeoutError):
                await SellerSession(client, timeout=0.01).messages.list("c", limit=1)
