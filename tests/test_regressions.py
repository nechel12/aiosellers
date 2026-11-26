import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from aiosellers import (
    FunPay,
    FunPayClientConfig,
    GGsel,
    GGselClientConfig,
    MemoryStateStore,
    Platform,
    Playerok,
    SellerHub,
)
from aiosellers.funpay.core.utils import classify_message
from aiosellers.funpay.entities.chat import Message as FunPayMessage
from aiosellers.funpay.entities.order import Order as FunPayOrder
from aiosellers.funpay.events import NewReviewEvent as FunPayReviewEvent
from aiosellers.funpay.listener import EventListener as FunPayListener
from aiosellers.funpay.parsers.orders import parse_order_api
from aiosellers.funpay.schemas import (
    Currency,
    MessageSnapshot,
    MessageTypes,
    OrderSide,
    OrderStatuses,
)
from aiosellers.ggsel.entities.product import Product
from aiosellers.playerok.api.chats import ChatAPI
from aiosellers.playerok.api.deals import DealAPI
from aiosellers.playerok.api.games import GameAPI
from aiosellers.playerok.events import NewMessageEvent
from aiosellers.playerok.graphql import GraphQLQuery
from aiosellers.playerok.listener import _STOP
from aiosellers.playerok.listener import EventListener as PlayerokListener
from aiosellers.playerok.raw.account import RawAccountService
from aiosellers.playerok.schemas import Chat as ChatSchema
from aiosellers.playerok.schemas import ChatMessage as ChatMessageSchema
from aiosellers.playerok.schemas import Item, ItemDeal


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _PlayerokRaw:
    def __init__(self, *, chats=None, messages=None, deals=None, deal=None):
        self.chats = self
        self.deals = self
        self._chats = list(chats or [])
        self._messages = list(messages or [])
        self._deals = list(deals or [])
        self._deal = deal
        self.get_chat_calls = 0

    async def get_chats(self, **kwargs):
        return SimpleNamespace(chats=list(self._chats))

    async def get_chat(self, chat_id):
        self.get_chat_calls += 1
        return None

    async def get_chat_messages(self, chat_id, count=24, after_cursor=None):
        return SimpleNamespace(
            messages=list(self._messages),
            page_info=SimpleNamespace(has_next_page=False, end_cursor=None),
        )

    async def get_deals(self, **kwargs):
        return SimpleNamespace(deals=list(self._deals))

    async def get_deal(self, deal_id):
        return self._deal


class _PlayerokClient:
    me_id = "me"
    _me_id = "me"
    _use_identity_map = False

    def __init__(self, raw):
        self._raw = raw
        self.chats = ChatAPI(self)
        self.deals = DealAPI(self)

    def _require_raw(self):
        return self._raw


def _playerok_message(message_id: str, text: str | None = "hi", **kwargs):
    payload = {
        "id": message_id,
        "text": text,
        "createdAt": _utc_now(),
        "isRead": False,
    }
    payload.update(kwargs)
    return ChatMessageSchema.model_validate(payload)


class PlayerokRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_baseline_deal_without_review_is_polled_later(self):
        deal = ItemDeal.model_validate(
            {
                "id": "d1",
                "status": "PAID",
                "direction": "IN",
                "item": {"id": "i1", "name": "Item"},
            }
        )
        reviewed = ItemDeal.model_validate(
            {
                "id": "d1",
                "status": "CONFIRMED",
                "direction": "IN",
                "chat": {"id": "c1", "type": "PM"},
                "item": {"id": "i1", "name": "Item"},
                "testimonial": {"id": "r1", "status": "APPROVED", "rating": 5},
            }
        )
        raw = _PlayerokRaw(deals=[deal], deal=reviewed)
        listener = PlayerokListener(
            _PlayerokClient(raw),
            review_delay=0,
            review_tries=0,
            refetch_message_delay=0,
            refetch_deal_delay=0,
            refetch_attempts=1,
        )

        await listener._refresh_known_deals()
        self.assertEqual(listener.review_deal_ids, ["d1"])

        events = await listener.poll_reviews_once()
        self.assertEqual([event.type.name for event in events], ["NEW_REVIEW"])
        self.assertEqual(events[0].review.rating, 5)
        self.assertEqual(listener.review_deal_ids, [])

    async def test_resync_emits_all_messages_newer_than_processed(self):
        m2 = _playerok_message("m2")
        m3 = _playerok_message("m3")
        raw = _PlayerokRaw(
            chats=[
                ChatSchema.model_validate(
                    {"id": "c1", "type": "PM", "lastMessage": m3.model_dump(by_alias=True)}
                )
            ],
            messages=[m2, m3],
        )
        client = _PlayerokClient(raw)
        listener = PlayerokListener(
            client,
            refetch_message_delay=0,
            refetch_deal_delay=0,
            refetch_attempts=1,
            new_chat_pause=0,
        )
        listener.processed_message_ids.add("m1")

        events = await listener._resync()
        message_ids = [event.message.id for event in events if isinstance(event, NewMessageEvent)]
        self.assertEqual(message_ids, ["m2", "m3"])

    async def test_unread_chat_filter_reads_following_pages(self):
        def chat(index: int, unread: int) -> ChatSchema:
            return ChatSchema.model_validate(
                {"id": str(index), "type": "PM", "unreadMessagesCounter": unread}
            )

        class PagedChats:
            def __init__(self):
                self.pages = {
                    None: SimpleNamespace(
                        chats=[chat(i, 1 if i == 0 else 0) for i in range(24)],
                        page_info=SimpleNamespace(has_next_page=True, end_cursor="p2"),
                    ),
                    "p2": SimpleNamespace(
                        chats=[chat(100 + i, 1) for i in range(5)],
                        page_info=SimpleNamespace(has_next_page=False, end_cursor=None),
                    ),
                }

            async def get_chats(self, **kwargs):
                return self.pages[kwargs.get("cursor")]

        raw = SimpleNamespace(chats=PagedChats())
        client = _PlayerokClient(raw)
        chats = await client.chats.list(limit=10, unread_only=True)
        self.assertEqual(len(chats), 6)
        self.assertEqual(chats[-1].id, "104")

    async def test_chat_get_deals_keeps_item_id(self):
        chat = ChatSchema.model_validate(
            {
                "id": "c1",
                "type": "PM",
                "deals": [
                    ItemDeal.model_validate(
                        {
                            "id": "d1",
                            "status": "PAID",
                            "direction": "IN",
                            "item": {"id": "i1", "name": "Item"},
                        }
                    )
                ],
            }
        )

        class Raw:
            async def get_chat(self, chat_id):
                return chat

        client = _PlayerokClient(SimpleNamespace(chats=Raw(), deals=None))
        entity = await client.chats.get("c1")
        deals = await entity.get_deals()
        self.assertEqual(deals[0].item_id, "i1")

    def test_item_schema_extracts_game_id(self):
        item = Item.model_validate({"id": "i1", "game": {"id": "g1"}})
        self.assertEqual(item.game_id, "g1")

    async def test_own_and_image_messages_are_handled(self):
        class Raw:
            async def get_chat_messages(self, *args, **kwargs):
                return SimpleNamespace(messages=[])

        client = _PlayerokClient(SimpleNamespace(chats=Raw(), deals=None))
        listener = PlayerokListener(client, refetch_attempts=1)
        chat = client.chats._create_chat(ChatSchema.model_validate({"id": "c1", "type": "PM"}))
        own = _playerok_message("own", user={"id": "me", "username": "Me", "role": "USER"})
        self.assertEqual(await listener.events_for_message(chat, own), [])
        self.assertIn("own", listener.processed_message_ids)

        image = _playerok_message("image", text=None, file={"id": "f1", "url": "https://x"})
        events = await listener.events_for_message(chat, image)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].message.file.id, "f1")


class PlayerokRawRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_user_returns_none_instead_of_attribute_error(self):
        class Transport:
            async def request(self, *args, **kwargs):
                return SimpleNamespace(status_code=200, json=lambda: {"data": {"user": None}})

        service = RawAccountService(Transport())
        self.assertIsNone(await service.get_account(username="ghost"))
        self.assertIsNone(await service.get_user(username="ghost"))

    async def test_game_limit_methods_are_bounded(self):
        class Games:
            async def get_game_category_obtaining_types(self, **kwargs):
                return SimpleNamespace(
                    obtaining_types=[
                        SimpleNamespace(id=str(i), name=str(i), description=None) for i in range(24)
                    ],
                    page_info=SimpleNamespace(has_next_page=False, end_cursor=None),
                )

            async def get_game_category_agreements(self, **kwargs):
                return SimpleNamespace(
                    agreements=[
                        SimpleNamespace(id=str(i), description="d", icon_type="INFO")
                        for i in range(24)
                    ],
                    page_info=SimpleNamespace(has_next_page=False, end_cursor=None),
                )

            async def get_game_category_instructions(self, **kwargs):
                return SimpleNamespace(
                    instructions=[SimpleNamespace(id=str(i), text="t") for i in range(24)],
                    page_info=SimpleNamespace(has_next_page=False, end_cursor=None),
                )

        client = SimpleNamespace(
            _use_identity_map=False,
            _require_raw=lambda: SimpleNamespace(games=Games()),
            _require_me_id=lambda: "me",
        )
        api = GameAPI(client)
        self.assertEqual(len(await api.get_obtaining_types("c", limit=1)), 1)
        self.assertEqual(len(await api.get_agreements("c", limit=1)), 1)
        self.assertEqual(len(await api.get_instructions("c", "o", limit=1)), 1)

    def test_false_boolean_item_filters_are_sent(self):
        payload = GraphQLQuery.get_items(game_id="g1", has_discount=False, has_reviews=False)
        filters = payload["variables"]["filter"]
        self.assertIs(filters["hasDiscount"], False)
        self.assertIs(filters["hasTestimonials"], False)

    def test_owner_statuses_can_be_overridden(self):
        payload = GraphQLQuery.get_items(user_id="seller", statuses=["PENDING_MODERATION"])
        self.assertEqual(payload["variables"]["filter"]["status"], ["PENDING_MODERATION"])

    def test_comment_filter_is_omitted_unless_requested(self):
        default = GraphQLQuery.get_testimonials("seller")
        required = GraphQLQuery.get_testimonials("seller", comment_required=True)
        self.assertNotIn("hasComment", default["variables"]["filter"])
        self.assertIs(required["variables"]["filter"]["hasComment"], True)


class PlayerokLifecycleRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_client_close_stops_its_listener(self):
        from unittest import mock

        client = Playerok("token")
        listener = mock.AsyncMock()
        client._listener = listener
        await client.close()
        listener.aclose.assert_awaited_once()

    async def test_aclose_wakes_a_blocked_consumer(self):
        class Raw:
            async def get_chat_messages(self, *args, **kwargs):
                return SimpleNamespace(messages=[])

        listener = PlayerokListener(_PlayerokClient(SimpleNamespace(chats=Raw(), deals=None)))
        queue: asyncio.Queue[object] = asyncio.Queue()
        listener._queue = queue
        await listener.aclose()
        item = await asyncio.wait_for(queue.get(), timeout=1)
        self.assertIs(item, _STOP)


class FunPayRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_is_single_flight(self):
        from unittest import mock

        class Transport:
            instances = 0
            account_id = 5

            def __init__(self, config):
                Transport.instances += 1

            async def refresh_profile(self, force=False):
                return None

            async def close(self):
                return None

        with mock.patch("aiosellers.funpay.funpay.FunPayTransport", Transport):
            client = FunPay(FunPayClientConfig(golden_key="key"))
            await asyncio.gather(client.start(), client.start())
            self.assertEqual(Transport.instances, 1)
            await client.close()

    async def test_iter_limit_is_a_total_limit(self):
        async def fake_list(*, side, cursor=None, limit=None, **filters):
            del side, filters
            calls.append(limit)
            if cursor is None:
                return "next", [object(), object()]
            return None, [object(), object()]

        client = FunPay(FunPayClientConfig(golden_key="key"))
        calls = []
        client.orders.list = fake_list  # type: ignore[method-assign]
        rows = [row async for row in client.orders.iter(limit=3)]
        self.assertEqual(len(rows), 3)
        self.assertEqual(calls, [3, 1])

    async def test_review_star_filter_forces_a_fresh_order_lookup(self):
        client = FunPay(FunPayClientConfig(golden_key="key"))
        calls = []

        class Orders:
            async def get(self, order_id, force_refresh=False):
                calls.append((order_id, force_refresh))
                return SimpleNamespace(review=SimpleNamespace(stars=5))

        client.orders = Orders()
        seen = []

        @client.on_new_review(stars=5)
        async def handler(event):
            seen.append(event)

        event = FunPayReviewEvent(
            client=client,
            message=FunPayMessage(id=1, text="review", chat_id=1),
            order_id="ABCD1234",
        )
        await client._dispatch(event)
        self.assertEqual(calls, [("ABCD1234", True)])
        self.assertEqual(seen, [event])

    async def test_text_and_image_are_rejected_instead_of_silently_dropped(self):
        client = FunPay(FunPayClientConfig(golden_key="key"))
        with self.assertRaises(ValueError):
            await client.chats.send_message(1, text="hello", image=b"png")

    async def test_leave_as_unread_is_explicitly_unsupported(self):
        from aiosellers.funpay.raw.chats import RawChats

        with self.assertRaises(ValueError):
            await RawChats(SimpleNamespace()).send(1, "hello", None, True)

    async def test_partial_remember_does_not_erase_full_order_fields(self):
        client = FunPay(FunPayClientConfig(golden_key="key"))
        full = FunPayOrder(
            id="ABCD1234",
            status=OrderStatuses.PAID,
            side=OrderSide.SALE,
            description="full",
            price=10,
            currency=Currency.RUB,
            buyer_username="Bob",
            buyer_id=1,
            chat_id=77,
            amount=2,
            seller_username="me",
            seller_id=5,
        )
        client.remember("orders", full.id, full)

        shortcut = FunPayOrder(
            id="ABCD1234",
            status=OrderStatuses.PAID,
            side=OrderSide.SALE,
            description="short",
            price=10,
            currency=Currency.RUB,
            buyer_username="Bob",
            buyer_id=1,
        )
        remembered = client.remember("orders", shortcut.id, shortcut, partial=True)

        self.assertIs(remembered, full)
        self.assertEqual(full.description, "short")
        self.assertEqual(full.chat_id, 77)
        self.assertEqual(full.amount, 2)
        self.assertEqual(full.seller_username, "me")

    async def test_chat_history_gap_grows_the_page_window(self):
        class Chats:
            def __init__(self):
                self.calls = []

            async def history(self, chat_id, last, retry=True):
                self.calls.append(last)
                hi = last - 1
                lo = max(1, hi - 99)
                return [
                    MessageSnapshot(
                        id=index,
                        text="x",
                        chat_id=3,
                        chat_name=None,
                        author="a",
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
                    for index in range(lo, hi + 1)
                ]

        client = FunPay(FunPayClientConfig(golden_key="key"))
        listener = FunPayListener(client, chat_history_batches=1, chat_history_max_batches=10)
        raw = SimpleNamespace(chats=Chats())

        rows, complete = await listener._history_since(raw, 3, 500, 1)
        self.assertFalse(complete)
        self.assertEqual(len(rows), 100)
        for _ in range(3):
            rows, complete = await listener._history_since(raw, 3, 500, 1)
        self.assertTrue(complete)
        self.assertEqual(len(rows), 499)

    async def test_malformed_sent_state_is_ignored(self):
        store = MemoryStateStore()
        await store.set(
            "funpay:5:listener",
            {
                "version": 1,
                "chats": {},
                "orders": {},
                "purchases": {},
                "ready": [False, False, False],
                "last_counts": None,
                "sent": [[None, 1]],
            },
        )
        client = FunPay(FunPayClientConfig(golden_key="key"))
        client._account_id = 5
        listener = FunPayListener(client, state=store)
        self.assertTrue(await listener._ensure_state_loaded(5))
        self.assertEqual(listener.sent_ids, {})

    def test_order_parser_uses_chat_node_id(self):
        snapshot = parse_order_api(
            {
                "order_uid": "ABCD1234",
                "status": "paid",
                "amount": 10,
                "currency": "RUB",
                "buyer": {"name": "Bob", "user_id": 9},
                "seller": {"name": "Me", "user_id": 5},
                "chat": {"node_name": "users-5-9", "node_id": 123},
                "type_data": {"fields": {}, "node": {}},
            }
        )
        self.assertEqual(snapshot.chat_id, 123)

    def test_ukrainian_purchase_message_is_classified(self):
        text = (
            "Покупець Bob оплатив замовлення #AB12CD34. "
            "Bob, не забудьте натиснути кнопку "
            "«Підтвердити виконання замовлення»."
        )
        self.assertIs(classify_message(text), MessageTypes.ORDER_PURCHASED)

    async def test_message_list_pages_until_limit(self):
        class Chats:
            async def history(self, chat_id, last, retry=True):
                if last > 3:
                    return [
                        MessageSnapshot(
                            id=index,
                            text="x",
                            chat_id=3,
                            chat_name=None,
                            author="a",
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
                        for index in (3, 4)
                    ]
                return [
                    MessageSnapshot(
                        id=index,
                        text="x",
                        chat_id=3,
                        chat_name=None,
                        author="a",
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
                    for index in (1, 2)
                ]

        client = FunPay(FunPayClientConfig(golden_key="key"))
        client._account_id = 5
        client._raw = SimpleNamespace(chats=Chats())
        messages = await client.chats.messages.list(3, limit=4)
        self.assertEqual([message.id for message in messages], [1, 2, 3, 4])


class GGselRegressionTests(unittest.TestCase):
    def test_partial_remember_keeps_product_fields(self):
        client = GGsel(GGselClientConfig(api_key="key", seller_id=42))
        full = Product(id=1, name="old", url="https://example/item", category_id=5)
        client.remember("products", full.id, full)
        shortcut = Product(id=1, name="new")
        remembered = client.remember("products", shortcut.id, shortcut, partial=True)
        self.assertIs(remembered, full)
        self.assertEqual(full.name, "new")
        self.assertEqual(full.url, "https://example/item")
        self.assertEqual(full.category_id, 5)


class GGselListenerRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_history_pages_across_the_limit(self):
        from aiosellers.ggsel.schemas import ChatMessageSchema as GGselMessage

        class Chats:
            async def history(self, chat_id, **kwargs):
                to_id = kwargs.get("to_id")
                if to_id is None:
                    return [
                        GGselMessage(id=3, message="3", buyer=1),
                        GGselMessage(id=4, message="4", buyer=1),
                    ]
                return [
                    GGselMessage(id=1, message="1", buyer=1),
                    GGselMessage(id=2, message="2", buyer=1),
                ]

        client = GGsel(GGselClientConfig(api_key="key", seller_id=42))
        client._raw = SimpleNamespace(chats=Chats())
        client._transport = SimpleNamespace()
        messages = await client.chats.history(7, limit=4)
        self.assertEqual([message.id for message in messages], [1, 2, 3, 4])

    async def test_new_chat_replays_only_recent_history(self):
        from datetime import timedelta

        from aiosellers.ggsel.entities.chat import Chat
        from aiosellers.ggsel.listener import EventListener as GGselListener
        from aiosellers.ggsel.schemas import ChatItem, ChatMessageSchema

        old = ChatMessageSchema(
            id=1,
            message="old",
            buyer=1,
            date_written=_utc_now() - timedelta(hours=1),
        )
        recent = ChatMessageSchema(id=2, message="recent", buyer=1, date_written=_utc_now())

        class Chats:
            async def history(self, chat_id, **kwargs):
                return [old, recent]

        client = GGsel(GGselClientConfig(api_key="key", seller_id=42))
        client._raw = SimpleNamespace(chats=Chats())
        client._transport = SimpleNamespace()
        listener = GGselListener(client, history_grace_seconds=60)
        item = ChatItem(id_i=7, last_message=_utc_now(), cnt_msg=2)
        state, events = await listener._new_chat_state(item, Chat(id=7))
        self.assertEqual(state.last_id, 2)
        self.assertEqual([event.message.id for event in events], [2])


class HubRegressionTests(unittest.TestCase):
    def test_auto_session_id_skips_explicit_ids(self):
        hub = SellerHub()
        hub.add(SimpleNamespace(), platform=Platform.FUNPAY, session_id="funpay-1")
        session = hub.add(SimpleNamespace(), platform=Platform.FUNPAY)
        self.assertEqual(session.id, "funpay-2")

    def test_client_platform_must_match(self):
        hub = SellerHub()
        client = FunPay(FunPayClientConfig(golden_key="key"))
        with self.assertRaises(ValueError):
            hub.add(client, platform=Platform.PLAYEROK)


if __name__ == "__main__":
    unittest.main()
