import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from aiosellers import MemoryStateStore
from aiosellers.funpay import FunPay
from aiosellers.funpay.client_config import FunPayClientConfig
from aiosellers.funpay.listener import EventListener
from aiosellers.funpay.parsers.orders import parse_order_list
from aiosellers.funpay.schemas import (
    EventTypes as FunPayEventTypes,
)
from aiosellers.funpay.schemas import (
    MessageSnapshot,
    MessageTypes,
    OrderSide,
)
from aiosellers.playerok import Playerok
from aiosellers.playerok.client_config import PlayerokClientConfig
from aiosellers.playerok.listener import EventListener as PlayerokListener
from aiosellers.playerok.schemas import Chat as ChatSchema
from aiosellers.playerok.schemas import ChatMessage as ChatMessageSchema
from aiosellers.playerok.schemas import ChatTypes, ItemDeal
from aiosellers.playerok.schemas import EventTypes as PlayerokEventTypes

BOOKMARK = """
<a class="contact-item" data-id="3" data-node-msg="{node}" data-user-msg="9">
  <div class="media-user-name">Ann</div>
  <div class="contact-item-message">{text}</div>
</a>
"""

ORDER_ROW = """
<a class="tc-item info" href="/orders/{order_id}/">
  <div class="tc-order">#{order_id}</div>
  <div class="order-desc"><div>аккаунт</div></div>
  <div class="tc-price">10 ₽</div>
  <div class="media-user-name"><span data-href="/users/9/">Bob</span></div>
</a>
"""


def _funpay_runner(html: str, *, buyer: int = 1, seller: int = 2) -> dict:
    return {
        "objects": [
            {"type": "chat_bookmarks", "tag": "chat-tag", "data": html},
            {
                "type": "orders_counters",
                "tag": "order-tag",
                "data": {"buyer": buyer, "seller": seller},
            },
        ]
    }


def _funpay_snapshot(message_id: int, text: str = "text") -> MessageSnapshot:
    return MessageSnapshot(
        id=message_id,
        text=text,
        chat_id=3,
        chat_name="Ann",
        author="Ann",
        author_id=9,
        interlocutor_id=9,
        image_link=None,
        image_name=None,
        type=MessageTypes.NON_SYSTEM,
        by_bot=False,
        badge=None,
        is_support=False,
        is_moderation=False,
        is_arbitration=False,
        is_auto_reply=False,
        html="",
    )


class _FunPayRaw:
    def __init__(self) -> None:
        self.account = self
        self.chats = self
        self.orders = self
        self.payloads: list[dict] = []
        self.history_result: list[MessageSnapshot] = []
        self.sales_page: tuple = (None, [])
        self.sales_calls: list = []

    async def runner_poll(self, objects, request=None):
        del objects, request
        return self.payloads.pop(0)

    async def history(self, chat_id, last_message_id, retry=True):
        del chat_id, last_message_id, retry
        return list(self.history_result)

    async def sales(self, cursor=None, query=None, retry=True):
        del query, retry
        self.sales_calls.append(cursor)
        return self.sales_page

    async def purchases(self, cursor=None, retry=True):
        del cursor, retry
        return None, []


class _FunPayTransport:
    account_id = 5
    username = "me"
    locale = "ru"
    rate_limited_until = 0
    categories: list = []

    async def refresh_profile(self, force: bool = False) -> None:
        del force


def _funpay_listener(raw: _FunPayRaw, store, **options) -> EventListener:
    client = FunPay(FunPayClientConfig(golden_key="key"))
    client._account_id = 5
    client._raw = raw  # type: ignore[assignment]
    client._transport = _FunPayTransport()  # type: ignore[assignment]
    return EventListener(client, state=store, **options)


class FunPayStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_resumes_the_chat_cursor(self):
        store = MemoryStateStore()
        raw = _FunPayRaw()
        raw.payloads.append(_funpay_runner(BOOKMARK.format(node=10, text="hi")))
        listener = _funpay_listener(raw, store)
        first = await listener.tick(orders=False, purchases=False)
        self.assertEqual([event.type for event in first], [FunPayEventTypes.INITIAL_CHAT])

        restarted_raw = _FunPayRaw()
        restarted_raw.history_result = [_funpay_snapshot(12, "missed")]
        restarted_raw.payloads.append(
            _funpay_runner(BOOKMARK.format(node=12, text="missed"))
        )
        restarted = _funpay_listener(restarted_raw, store)
        events = await restarted.tick(orders=False, purchases=False)

        self.assertEqual(
            [event.type for event in events],
            [
                FunPayEventTypes.CHATS_LIST_CHANGED,
                FunPayEventTypes.LAST_CHAT_MESSAGE_CHANGED,
                FunPayEventTypes.NEW_MESSAGE,
            ],
        )
        self.assertEqual(events[-1].message.id, 12)

    async def test_restart_without_changes_emits_nothing(self):
        store = MemoryStateStore()
        raw = _FunPayRaw()
        raw.payloads.append(_funpay_runner(BOOKMARK.format(node=10, text="hi")))
        await _funpay_listener(raw, store).tick(orders=False, purchases=False)

        restarted_raw = _FunPayRaw()
        restarted_raw.payloads.append(_funpay_runner(BOOKMARK.format(node=10, text="hi")))
        events = await _funpay_listener(restarted_raw, store).tick(
            orders=False, purchases=False
        )
        self.assertEqual(events, [])

    async def test_restart_keeps_the_order_snapshot(self):
        store = MemoryStateStore()
        raw = _FunPayRaw()
        raw.payloads.append(_funpay_runner(""))
        raw.sales_page = parse_order_list(
            ORDER_ROW.format(order_id="ABCD1234"), side=OrderSide.SALE
        )
        first = await _funpay_listener(raw, store).tick(
            messages=False, purchases=False
        )
        self.assertEqual([event.type for event in first], [FunPayEventTypes.INITIAL_ORDER])

        restarted_raw = _FunPayRaw()
        restarted_raw.payloads.append(_funpay_runner(""))
        restarted_raw.sales_page = parse_order_list(
            ORDER_ROW.format(order_id="ABCD1234"), side=OrderSide.SALE
        )
        events = await _funpay_listener(restarted_raw, store).tick(
            messages=False, purchases=False
        )
        self.assertEqual(
            [event.type for event in events], [FunPayEventTypes.ORDERS_LIST_CHANGED]
        )

    async def test_sent_message_ids_survive_restart(self):
        store = MemoryStateStore()
        raw = _FunPayRaw()
        listener = _funpay_listener(raw, store)
        listener.remember_sent(3, 77)
        raw.payloads.append(_funpay_runner(""))
        await listener.tick(orders=False, purchases=False)

        restarted_raw = _FunPayRaw()
        restarted_raw.payloads.append(_funpay_runner(""))
        restarted = _funpay_listener(restarted_raw, store)
        await restarted.tick(orders=False, purchases=False)

        self.assertTrue(restarted.was_sent(3, 77))
        self.assertTrue(restarted.was_sent("3", 77))
        self.assertFalse(restarted.was_sent(3, 78))

    async def test_sent_history_is_bounded(self):
        store = MemoryStateStore()
        raw = _FunPayRaw()
        listener = _funpay_listener(raw, store, sent_history_limit=2)
        for message_id in (1, 2, 3):
            listener.remember_sent(3, message_id)
        raw.payloads.append(_funpay_runner(""))
        await listener.tick(orders=False, purchases=False)

        snapshot = await store.get("funpay:5:listener")
        self.assertEqual(snapshot["sent"], [[3, 2], [3, 3]])

    async def test_malformed_state_falls_back_to_a_fresh_start(self):
        store = MemoryStateStore()
        await store.set("funpay:5:listener", {"version": 1, "chats": "broken"})
        raw = _FunPayRaw()
        raw.payloads.append(_funpay_runner(BOOKMARK.format(node=10, text="hi")))

        events = await _funpay_listener(raw, store).tick(
            orders=False, purchases=False
        )
        self.assertEqual([event.type for event in events], [FunPayEventTypes.INITIAL_CHAT])


def _playerok_message(message_id: str, text: str, deal_id: str | None = None):
    payload = {
        "id": message_id,
        "text": text,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "isRead": False,
    }
    if deal_id:
        payload["deal"] = {
            "id": deal_id,
            "status": "PAID",
            "direction": "OUT",
            "hasProblem": False,
        }
    return ChatMessageSchema.model_validate(payload)


def _playerok_deal(deal_id: str = "deal-1", *, reviewed: bool = False) -> ItemDeal:
    payload = {
        "id": deal_id,
        "status": "PAID",
        "direction": "OUT",
        "hasProblem": False,
        "chat": {"id": "c1", "type": "PM"},
    }
    if reviewed:
        payload["testimonial"] = {
            "id": "review-1",
            "status": "APPROVED",
            "rating": 5,
            "text": "ok",
        }
    return ItemDeal.model_validate(payload)


class _PlayerokRaw:
    def __init__(self, deal: ItemDeal | None = None) -> None:
        self.deal = deal
        self.chats = self
        self.deals = self

    async def get_chat_messages(self, chat_id, count=12):
        del chat_id, count
        return SimpleNamespace(messages=[])

    async def get_deal(self, deal_id):
        del deal_id
        return self.deal

    async def get_chats(self, **kwargs):
        del kwargs
        return SimpleNamespace(chats=[])

    async def get_chat(self, chat_id):
        del chat_id
        return None


def _playerok_client(raw: _PlayerokRaw) -> Playerok:
    client = Playerok(PlayerokClientConfig(access_token="token"))
    client._me_id = "me"
    client._raw = raw  # type: ignore[assignment]
    client._transport = SimpleNamespace(  # type: ignore[assignment]
        _access_token="token", config=SimpleNamespace(user_agent="test")
    )
    return client


def _playerok_listener(client: Playerok, store, **options) -> PlayerokListener:
    return PlayerokListener(
        client,
        refetch_message_delay=0,
        refetch_deal_delay=0,
        refetch_attempts=1,
        new_chat_pause=0,
        review_delay=0,
        state=store,
        **options,
    )


class PlayerokStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_processed_messages_survive_restart(self):
        store = MemoryStateStore()
        raw = _PlayerokRaw()
        client = _playerok_client(raw)
        listener = _playerok_listener(client, store)
        chat = client.chats._create_chat(ChatSchema(id="c1", type=ChatTypes.PM))
        message = _playerok_message("m1", "hello")

        first = await listener.events_for_message(chat, message)
        self.assertEqual([event.type for event in first], [PlayerokEventTypes.NEW_MESSAGE])

        restarted = _playerok_listener(_playerok_client(_PlayerokRaw()), store)
        restarted_chat = restarted.client.chats._create_chat(
            ChatSchema(id="c1", type=ChatTypes.PM)
        )
        self.assertEqual(
            await restarted.events_for_message(restarted_chat, message), []
        )

    async def test_deal_events_are_not_repeated_after_restart(self):
        store = MemoryStateStore()
        raw = _PlayerokRaw(deal=_playerok_deal())
        client = _playerok_client(raw)
        listener = _playerok_listener(client, store)
        chat = client.chats._create_chat(ChatSchema(id="c1", type=ChatTypes.PM))
        await listener.events_for_message(
            chat, _playerok_message("m1", "{{ITEM_PAID}}", "deal-1")
        )

        restarted = _playerok_listener(
            _playerok_client(_PlayerokRaw(deal=_playerok_deal())), store
        )
        restarted_chat = restarted.client.chats._create_chat(
            ChatSchema(id="c1", type=ChatTypes.PM)
        )
        repeated = await restarted.events_for_message(
            restarted_chat, _playerok_message("m2", "{{ITEM_PAID}}", "deal-1")
        )
        self.assertEqual(repeated, [])

    async def test_pending_review_is_polled_after_restart(self):
        store = MemoryStateStore()
        raw = _PlayerokRaw(deal=_playerok_deal())
        client = _playerok_client(raw)
        listener = _playerok_listener(client, store)
        chat = client.chats._create_chat(ChatSchema(id="c1", type=ChatTypes.PM))
        await listener.events_for_message(
            chat, _playerok_message("m1", "{{ITEM_PAID}}", "deal-1")
        )

        restarted = _playerok_listener(
            _playerok_client(_PlayerokRaw(deal=_playerok_deal(reviewed=True))), store
        )
        events = await restarted.poll_reviews_once()

        self.assertEqual([event.type for event in events], [PlayerokEventTypes.NEW_REVIEW])
        self.assertEqual(restarted.review_deal_ids, [])

    async def test_processed_history_is_bounded(self):
        store = MemoryStateStore()
        raw = _PlayerokRaw()
        client = _playerok_client(raw)
        listener = _playerok_listener(client, store, processed_history_limit=2)
        chat = client.chats._create_chat(ChatSchema(id="c1", type=ChatTypes.PM))
        for message_id in ("m1", "m2", "m3"):
            await listener.events_for_message(
                chat, _playerok_message(message_id, "hello")
            )

        snapshot = await store.get("playerok:me:listener")
        self.assertEqual(snapshot["messages"], ["m2", "m3"])

        restarted = _playerok_listener(
            _playerok_client(_PlayerokRaw()), store, processed_history_limit=2
        )
        restarted_chat = restarted.client.chats._create_chat(
            ChatSchema(id="c1", type=ChatTypes.PM)
        )
        replay = await restarted.events_for_message(
            restarted_chat, _playerok_message("m1", "hello")
        )
        self.assertEqual([event.type for event in replay], [PlayerokEventTypes.NEW_MESSAGE])
        self.assertEqual(
            await restarted.events_for_message(
                restarted_chat, _playerok_message("m3", "hello")
            ),
            [],
        )

    async def test_malformed_state_falls_back_to_a_fresh_start(self):
        store = MemoryStateStore()
        await store.set("playerok:me:listener", {"version": 1, "messages": "broken"})
        client = _playerok_client(_PlayerokRaw())
        listener = _playerok_listener(client, store)
        chat = client.chats._create_chat(ChatSchema(id="c1", type=ChatTypes.PM))

        events = await listener.events_for_message(
            chat, _playerok_message("m1", "hello")
        )
        self.assertEqual([event.type for event in events], [PlayerokEventTypes.NEW_MESSAGE])


if __name__ == "__main__":
    unittest.main()
