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
        config = FunPayConfig.from_client(
            FunPayClientConfig(golden_key="key", bot_mark=False)
        )
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
