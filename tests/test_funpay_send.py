import asyncio
import json
import unittest
from types import SimpleNamespace

from aiosellers.funpay.client_config import FunPayClientConfig
from aiosellers.funpay.core.config import FunPayConfig
from aiosellers.funpay.core.constants import BOT_MARK
from aiosellers.funpay.exceptions import MessageNotDeliveredError
from aiosellers.funpay.raw.chats import RawChats
from aiosellers.funpay.raw.orders import RawOrders

BOOKMARK = """
<a class="contact-item" data-id="3" data-node-msg="{node}" data-user-msg="9">
  <div class="media-user-name">Ann</div>
  <div class="contact-item-message">hi</div>
</a>
"""


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def json(self):
        return self._payload


class _Transport:
    account_id = 5
    username = "me"

    def __init__(self, pages: list[dict], *, bot_mark: bool = True) -> None:
        self.pages = pages
        self.gets = 0
        self.contents: list[str] = []
        self._config = SimpleNamespace(bot_mark=bot_mark)

    async def refresh_profile(self) -> None:
        return None

    async def request(self, method, url, **kwargs):
        del url
        if method == "GET":
            self.gets += 1
            return _Response(
                {
                    "chat": {
                        "node": {"name": "users-5-9"},
                        "messages": [
                            {
                                "id": 11,
                                "author": 5,
                                "html": '<div class="chat-msg-text">old</div>',
                            },
                            {
                                "id": 12,
                                "author": 5,
                                "html": '<div class="chat-msg-text">new</div>',
                            },
                        ],
                    }
                }
            )
        data = kwargs.get("data") or {}
        request = data.get("request") or ""
        if "chat_message" in request:
            self.contents.append(json.loads(request)["data"]["content"])
            return _Response({"objects": [], "response": {"error": None}})
        node = self.pages.pop(0)
        return _Response(
            {
                "objects": [
                    {
                        "type": "chat_bookmarks",
                        "data": {"html": BOOKMARK.format(node=node)},
                    }
                ],
                "response": False,
            }
        )


class FunPaySendTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_runner_uses_the_new_own_message(self) -> None:
        transport = _Transport([11, 12])
        sent = await RawChats(transport).send(3, "new", None, False)
        self.assertEqual(sent.id, 12)
        self.assertEqual(transport.gets, 1)

    async def test_send_fallback_is_serialized_per_chat_only(self) -> None:
        class _ConcurrentTransport:
            account_id = 5
            username = "me"
            _config = SimpleNamespace(bot_mark=False)

            def __init__(self) -> None:
                self.latest: dict[str, int] = {}
                self.active = 0
                self.max_active = 0

            async def refresh_profile(self) -> None:
                return None

            async def request(self, method, url, **kwargs):
                del method, url
                payload = json.loads(kwargs["data"]["request"])
                chat_id = str(payload["data"]["node"])
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                try:
                    await asyncio.sleep(0.01)
                    self.latest[chat_id] = self.latest.get(chat_id, 0) + 1
                    return _Response({"objects": [], "response": {"error": None}})
                finally:
                    self.active -= 1

        class _FallbackChats(RawChats):
            def __init__(self, transport) -> None:
                super().__init__(transport)
                self.before: list[int] = []

            async def _node_message_id(self, chat_id):
                before = self.transport.latest.get(str(chat_id), 0)
                self.before.append(before)
                return before

            async def _message_after(self, chat_id, before):
                del chat_id
                return SimpleNamespace(id=before + 1)

        transport = _ConcurrentTransport()
        raw = _FallbackChats(transport)
        sent = await asyncio.gather(
            raw.send(3, "one", None, False), raw.send(3, "two", None, False)
        )

        self.assertEqual(sorted(message.id for message in sent), [1, 2])
        self.assertEqual(raw.before, [0, 1])
        self.assertEqual(transport.max_active, 1)

        transport.max_active = 0
        await asyncio.gather(raw.send(3, "three", None, False), raw.send(4, "four", None, False))
        self.assertEqual(transport.max_active, 2)

    async def test_runner_error_is_not_treated_as_sent(self) -> None:
        transport = _Transport([11, 12])

        async def request(method, url, **kwargs):
            del method, url
            data = kwargs.get("data") or {}
            if "chat_message" in (data.get("request") or ""):
                return _Response({"objects": [], "response": {"error": "denied"}})
            return await _Transport.request(transport, "POST", "runner/", **kwargs)

        transport.request = request
        with self.assertRaises(MessageNotDeliveredError):
            await RawChats(transport).send(3, "new", None, False)
        self.assertEqual(transport.gets, 0)


class BotMarkTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_mark_is_on_by_default(self):
        transport = _Transport([11, 12])
        await RawChats(transport).send(3, "new", None, False)
        self.assertEqual(transport.contents, [f"{BOT_MARK}new"])

    async def test_message_mark_can_be_disabled(self):
        transport = _Transport([11, 12], bot_mark=False)
        await RawChats(transport).send(3, "new", None, False)
        self.assertEqual(transport.contents, ["new"])

    async def test_review_mark_can_be_disabled(self):
        transport = _ReviewTransport(bot_mark=False)
        await RawOrders(transport).review("ORDER1234", "thanks", 5)
        self.assertEqual(transport.text, "thanks")

        transport = _ReviewTransport()
        await RawOrders(transport).review("ORDER1234", "thanks", 5)
        self.assertEqual(transport.text, f"thanks{BOT_MARK}")

    def test_client_config_is_copied(self):
        config = FunPayConfig.from_client(FunPayClientConfig(golden_key="key", bot_mark=False))
        self.assertFalse(config.bot_mark)


class _ReviewTransport:
    account_id = 5

    def __init__(self, *, bot_mark: bool = True) -> None:
        self.text: str | None = None
        self._config = SimpleNamespace(bot_mark=bot_mark)

    async def refresh_profile(self) -> None:
        return None

    async def request(self, method, url, **kwargs):
        del method, url
        self.text = kwargs["data"]["text"]
        return _Response({"error": None})


if __name__ == "__main__":
    unittest.main()
