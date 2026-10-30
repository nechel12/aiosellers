import asyncio
import time
import unittest

from aiosellers.funpay import FunPay, FunPayClientConfig
from aiosellers.funpay.entities.chat import Chat as FunPayChat
from aiosellers.funpay.entities.chat import Message as FunPayMessage
from aiosellers.funpay.events import NewMessageEvent as FunPayMessageEvent
from aiosellers.playerok import Playerok
from aiosellers.playerok.client_config import PlayerokClientConfig
from aiosellers.playerok.entities.chat import Chat as PlayerokChat
from aiosellers.playerok.entities.chat import ChatMessage as PlayerokMessage
from aiosellers.playerok.events import NewMessageEvent as PlayerokMessageEvent


def _playerok_event(client):
    return PlayerokMessageEvent(
        client=client,
        chat=PlayerokChat(id="c1"),
        message=PlayerokMessage(id="m1", sent_at=None, is_read=True, text="hi", chat_id="c1"),
    )


def _funpay_event(client):
    return FunPayMessageEvent(
        client=client,
        chat=FunPayChat(id=1, name="Ann"),
        message=FunPayMessage(id=1, text="hi", chat_id=1),
    )


class PlayerokDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_handler_times_out_without_blocking_others(self):
        client = Playerok(
            PlayerokClientConfig(
                access_token="token", handler_timeout=0.05, max_concurrent_handlers=4
            )
        )
        done = []

        @client.on_message()
        async def slow(_event):
            await asyncio.sleep(5)
            done.append("slow")

        @client.on_message()
        async def fast(_event):
            await asyncio.sleep(0)
            done.append("fast")

        started = time.monotonic()
        await client._dispatch(_playerok_event(client))
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 1.0)
        self.assertEqual(done, ["fast"])

    async def test_handlers_run_concurrently(self):
        client = Playerok(
            PlayerokClientConfig(
                access_token="token", handler_timeout=5.0, max_concurrent_handlers=4
            )
        )
        first_started = asyncio.Event()
        second_started = asyncio.Event()

        @client.on_message()
        async def first(_event):
            first_started.set()
            await asyncio.wait_for(second_started.wait(), 1.0)

        @client.on_message()
        async def second(_event):
            second_started.set()
            await asyncio.wait_for(first_started.wait(), 1.0)

        await client._dispatch(_playerok_event(client))

        self.assertTrue(first_started.is_set())
        self.assertTrue(second_started.is_set())


class FunPayDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_handler_times_out_without_blocking_others(self):
        client = FunPay(
            FunPayClientConfig(
                golden_key="key", handler_timeout=0.05, max_concurrent_handlers=4
            )
        )
        done = []

        @client.on_message()
        async def slow(_event):
            await asyncio.sleep(5)
            done.append("slow")

        @client.on_message()
        async def fast(_event):
            await asyncio.sleep(0)
            done.append("fast")

        started = time.monotonic()
        await client._dispatch(_funpay_event(client))
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 1.0)
        self.assertEqual(done, ["fast"])
