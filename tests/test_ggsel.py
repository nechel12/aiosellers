import asyncio
import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from aiosellers import (
    GGsel,
    GGselClientConfig,
    MemoryStateStore,
)
from aiosellers.ggsel.core.config import GGselConfig
from aiosellers.ggsel.core.exceptions import (
    ApiError,
    RateLimitedError,
    RequestFailedError,
)
from aiosellers.ggsel.entities import Review, Sale
from aiosellers.ggsel.entities.chat import Chat, ChatMessage
from aiosellers.ggsel.events import (
    InitialChatEvent,
    NewMessageEvent,
    NewReviewEvent,
    NewSaleEvent,
)
from aiosellers.ggsel.listener import EventListener
from aiosellers.ggsel.raw.sales import RawSaleService
from aiosellers.ggsel.schemas import (
    BalanceContent,
    BalanceResponse,
    CategoriesResponse,
    CategorySchema,
    ChatItem,
    ChatList,
    ChatMessageSchema,
    LastSalesResponse,
    MessageDirection,
    PriceUpdateResponse,
    ProductData,
    ProductDataResponse,
    ProductListResponse,
    ProductRow,
    PurchaseBuyerInfo,
    PurchaseContent,
    PurchaseInfoResponse,
    PurchaseOption,
    ReceiptItem,
    ReceiptOperation,
    ReceiptProduct,
    ReceiptsContent,
    ReceiptsResponse,
    ReviewSchema,
    ReviewsResponse,
    SaleInfo,
    SaleProduct,
    SaleSchema,
    SellerGoodsResponse,
    SendMessageResponse,
    TaskStatusResponse,
    UniqueCodeResponse,
)
from aiosellers.ggsel.schemas import (
    EventTypes as GGselEvents,
)
from aiosellers.ggsel.transport import tls
from aiosellers.ggsel.transport.tls import GGselTransport


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _Response:
    def __init__(self, status_code=200, payload=None, text=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload) if payload is not None else (text or "")
        self.headers = headers or {}

    def json(self):
        if self._payload is not None:
            return self._payload
        return json.loads(self.text)


def _login_ok(token: str = "tok", seller_id: int = 42) -> _Response:
    return _Response(
        payload={
            "retval": 1,
            "desc": "ok",
            "token": token,
            "seller_id": seller_id,
            "valid_thru": "2099-01-01 00:00:00",
        }
    )


class _FakeTLSClient:
    last = None
    responses: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.header_calls = []
        self.responses = list(type(self).responses)
        self.closed = False
        _FakeTLSClient.last = self

    async def get(self, *, url, headers=None, params=None):
        self.calls.append(("get", url, params, None))
        self.header_calls.append(headers or {})
        return self._next()

    async def post(self, *, url, headers=None, params=None, json=None):
        self.calls.append(("post", url, params, json))
        self.header_calls.append(headers or {})
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


class _TransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _FakeTLSClient.responses = []
        patcher = mock.patch("tls_requests.AsyncClient", _FakeTLSClient)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_transport(self, *, base_url="https://seller.ggsel.com/") -> GGselTransport:
        return GGselTransport(
            api_key="secret",
            seller_id=42,
            config=GGselConfig(base_url=base_url),
        )

    def fake_sleep(self):
        delays = []

        async def fake(delay):
            delays.append(delay)

        patcher = mock.patch.object(tls.asyncio, "sleep", fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return delays

    async def test_login_signs_timestamp_and_sends_locale_headers(self):
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [_login_ok()]

        token = await transport.login()

        self.assertEqual(token, "tok")
        method, url, params, body = fake.calls[0]
        self.assertEqual(method, "post")
        self.assertTrue(url.endswith("/api_sellers/api/apilogin"))
        self.assertEqual(params, {})
        self.assertEqual(body["seller_id"], 42)
        expected = hashlib.sha256(("secret" + body["timestamp"]).encode()).hexdigest()
        self.assertEqual(body["sign"], expected)
        self.assertEqual(fake.header_calls[0]["lang"], "ru")
        self.assertEqual(fake.header_calls[0]["locale"], "ru-RU")

        await transport.close()
        self.assertTrue(fake.closed)

    async def test_base_url_without_trailing_slash_is_normalized(self):
        transport = self.make_transport(base_url="https://seller.ggsel.com")
        fake = transport._client
        fake.responses = [_login_ok()]

        await transport.login()

        self.assertEqual(
            fake.calls[0][1],
            "https://seller.ggsel.com/api_sellers/api/apilogin",
        )
        await transport.close()

    async def test_login_is_cached_until_expiry(self):
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [_login_ok()]

        await transport.login()
        await transport.login()

        self.assertEqual(len(fake.calls), 1)

    async def test_authenticated_request_adds_token_query(self):
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [
            _login_ok(),
            _Response(payload={"retval": 1, "content": {"amount_t_free": 5}}),
        ]

        data = await transport.request(
            "get", "/api_sellers/api/sellers/account/balance/info", params={"x": "1"}
        )

        self.assertEqual(data["content"]["amount_t_free"], 5)
        method, _, params, _ = fake.calls[1]
        self.assertEqual(method, "get")
        self.assertEqual(params["token"], "tok")
        self.assertEqual(params["x"], "1")

    async def test_401_reauthenticates_once(self):
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [
            _login_ok("first"),
            _Response(401),
            _login_ok("second"),
            _Response(payload={"retval": 1, "ok": True}),
        ]

        data = await transport.request("get", "/api_sellers/api/foo")

        self.assertTrue(data["ok"])
        self.assertEqual([call[0] for call in fake.calls], ["post", "get", "post", "get"])
        self.assertEqual(fake.calls[1][2]["token"], "first")
        self.assertEqual(fake.calls[3][2]["token"], "second")

    async def test_429_honours_retry_after(self):
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [
            _login_ok(),
            _Response(429, headers={"retry-after": "2.5"}),
            _Response(payload={"retval": 1}),
        ]
        delays = self.fake_sleep()

        await transport.request("get", "/api_sellers/api/foo")

        self.assertEqual(delays, [2.5])

    async def test_429_raises_after_three_attempts(self):
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [_login_ok(), _Response(429), _Response(429), _Response(429)]
        self.fake_sleep()

        with self.assertRaises(RateLimitedError):
            await transport.request("get", "/api_sellers/api/foo")

        self.assertEqual(len([call for call in fake.calls if call[0] == "get"]), 3)

    async def test_get_retries_network_errors(self):
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [_login_ok(), ConnectionError("boom"), _Response(payload={"retval": 1})]
        delays = self.fake_sleep()

        await transport.request("get", "/api_sellers/api/foo")

        self.assertEqual(len(delays), 1)

    async def test_post_is_not_retried(self):
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [_login_ok(), _Response(503)]

        with self.assertRaises(RequestFailedError):
            await transport.request("post", "/api_sellers/api/foo", json_body={})

        self.assertEqual(len([call for call in fake.calls if call[0] == "post"]), 2)

    async def test_last_sales_sends_documented_group_flag(self):
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [_login_ok(), _Response(payload={"retval": 1})]
        service = RawSaleService(transport)

        await service.last_sales(group=True, top=5)
        await service.last_sales(group=False, top=5)

        first = [call for call in fake.calls if call[0] == "get"][0]
        second = [call for call in fake.calls if call[0] == "get"][1]
        self.assertEqual(first[2]["group"], "true")
        self.assertEqual(first[2]["top"], 5)
        self.assertEqual(second[2]["group"], "false")

    async def test_negative_retval_is_an_api_error(self):
        transport = self.make_transport()
        fake = transport._client
        fake.responses = [
            _login_ok(),
            _Response(payload={"retval": -1, "retdesc": "bad sign"}),
        ]

        with self.assertRaises(ApiError) as raised:
            await transport.request("get", "/api_sellers/api/foo")

        self.assertEqual(raised.exception.retval, -1)
        self.assertIn("bad sign", str(raised.exception))


class _LifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _FakeTLSClient.responses = []
        patcher = mock.patch("tls_requests.AsyncClient", _FakeTLSClient)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_start_logs_in_and_close_releases_the_transport(self):
        _FakeTLSClient.responses = [_login_ok()]
        client = GGsel(GGselClientConfig(api_key="secret", seller_id=42))

        await client.start()

        self.assertEqual(client.seller_id, 42)
        self.assertIsNotNone(client._raw)
        fake = _FakeTLSClient.last

        await client.close()

        self.assertTrue(fake.closed)
        self.assertIsNone(client._raw)

    async def test_failed_start_closes_the_transport(self):
        _FakeTLSClient.responses = [_Response(payload={"retval": -1, "retdesc": "bad key"})]
        client = GGsel(GGselClientConfig(api_key="secret", seller_id=42))

        with self.assertRaises(ApiError):
            await client.start()

        self.assertIsNone(client._transport)
        self.assertTrue(_FakeTLSClient.last.closed)


class _FakeChatService:
    def __init__(self):
        self.items: list[ChatItem] = []
        self.cnt_pages = 1
        self.pages: dict[int, ChatList] = {}
        self.history_rows: list[ChatMessageSchema] = []
        self.history_calls = []
        self.sent = []
        self.fail_chats: set[int] = set()

    async def list_chats(self, **kwargs):
        page = kwargs.get("page") or 1
        if page in self.pages:
            return self.pages[page]
        return ChatList(cnt_pages=self.cnt_pages, items=list(self.items))

    async def history(self, chat_id, **kwargs):
        self.history_calls.append((int(chat_id), kwargs))
        if int(chat_id) in self.fail_chats:
            raise RequestFailedError("history is unavailable")
        rows = list(self.history_rows)
        from_id = kwargs.get("from_id")
        if from_id is not None:
            rows = [row for row in rows if row.id > int(from_id)]
        return rows

    async def send_message(self, chat_id, message):
        self.sent.append((int(chat_id), message))
        return SendMessageResponse(retval=1)


class _FakeSaleService:
    def __init__(self):
        self.sales: list[SaleSchema] = []
        self.purchase_response = PurchaseInfoResponse()
        self.unique_response = UniqueCodeResponse()
        self.calls = []

    async def last_sales(self, **kwargs):
        self.calls.append(kwargs)
        return LastSalesResponse(sales=list(self.sales))

    async def purchase(self, invoice_id):
        return self.purchase_response

    async def purchase_by_unique_code(self, unique_code):
        return self.unique_response


class _FakeReviewService:
    def __init__(self):
        self.pages: dict[int, ReviewsResponse] = {}
        self.calls = []

    async def reviews(self, **kwargs):
        self.calls.append(kwargs)
        page = kwargs.get("page") or 1
        return self.pages.get(page, ReviewsResponse())


class _FakeProductService:
    def __init__(self):
        self.list_response = ProductListResponse()
        self.goods_response = SellerGoodsResponse()
        self.data_response = ProductDataResponse()
        self.price_response = PriceUpdateResponse()
        self.task_response = TaskStatusResponse()
        self.list_calls = []
        self.get_calls = 0
        self.price_updates = []

    async def list_products(self, **kwargs):
        self.list_calls.append(kwargs)
        return self.list_response

    async def seller_goods(self, seller_id, **kwargs):
        self.list_calls.append((seller_id, kwargs))
        return self.goods_response

    async def get_product(self, product_id):
        self.get_calls += 1
        return self.data_response

    async def update_prices(self, items):
        self.price_updates.append(items)
        return self.price_response

    async def task_status(self, task_id):
        return self.task_response


class _FakeCategoryService:
    def __init__(self):
        self.pages: dict[int, CategoriesResponse] = {}

    async def categories(self, **kwargs):
        page = kwargs.get("page") or 1
        return self.pages.get(page, CategoriesResponse())


class _FakeAccountService:
    def __init__(self):
        self.balance_response = BalanceResponse()
        self.receipts_response = ReceiptsResponse()

    async def balance(self):
        return self.balance_response

    async def receipts(self, **kwargs):
        return self.receipts_response


class _FakeRaw:
    def __init__(self):
        self.chats = _FakeChatService()
        self.sales = _FakeSaleService()
        self.reviews = _FakeReviewService()
        self.products = _FakeProductService()
        self.categories = _FakeCategoryService()
        self.account = _FakeAccountService()


class _StartedTransport:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


def _client(raw: _FakeRaw | None = None, *, store=None, **config) -> GGsel:
    client = GGsel(GGselClientConfig(api_key="key", seller_id=42, state=store, **config))
    client._raw = raw or _FakeRaw()
    client._transport = _StartedTransport()
    return client


def _chat_item(
    chat_id: int = 7,
    *,
    last_message: datetime | None = None,
    cnt_msg: int = 2,
    cnt_new: int = 0,
) -> ChatItem:
    return ChatItem(
        id_i=chat_id,
        email="buyer@example.com",
        product=100,
        last_message=last_message or _now(),
        cnt_msg=cnt_msg,
        cnt_new=cnt_new,
    )


def _row(message_id: int, *, buyer: int = 0, seller: int = 0, text: str = "hi"):
    return ChatMessageSchema(
        id=message_id,
        message=text,
        buyer=buyer,
        seller=seller,
        date_written=_now(),
    )


def _sale(invoice_id: int, *, price: float = 100.0) -> SaleSchema:
    return SaleSchema(
        invoice_id=invoice_id,
        date=_now(),
        product=SaleProduct(id=9, name="Item", price_rub=price),
    )


def _review(review_id: int) -> ReviewSchema:
    return ReviewSchema(id=review_id, info="ok", good=9, type="good", date=_now())


class _ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_list_decodes_and_reuses_identity(self):
        raw = _FakeRaw()
        raw.chats.items = [_chat_item(cnt_new=1)]
        client = _client(raw)

        first = await client.chats.list()
        second = await client.chats.list()

        self.assertEqual(len(first), 1)
        self.assertIs(first[0], second[0])
        self.assertEqual(first[0].buyer_email, "buyer@example.com")
        self.assertEqual(first[0].unread_count, 1)

    async def test_chat_history_is_sorted_and_tagged(self):
        raw = _FakeRaw()
        raw.chats.history_rows = [_row(2, seller=1), _row(1, buyer=1)]
        client = _client(raw)

        messages = await client.chats.history(7)

        self.assertEqual([message.id for message in messages], [1, 2])
        self.assertTrue(all(message.chat_id == 7 for message in messages))
        self.assertEqual(messages[0].direction, MessageDirection.BUYER)
        self.assertEqual(messages[1].direction, MessageDirection.SELLER)

    async def test_chat_send_rejects_blank_text(self):
        raw = _FakeRaw()
        client = _client(raw)

        with self.assertRaises(ValueError):
            await client.chats.send(7, "   ")

        await client.chats.send(7, "hello")
        self.assertEqual(raw.chats.sent, [(7, "hello")])

    async def test_product_list_maps_sale_fields(self):
        raw = _FakeRaw()
        raw.products.list_response = ProductListResponse(
            rows=[
                ProductRow(
                    id_goods=1,
                    name_goods="A",
                    price="100",
                    currency="RUB",
                    visible=1,
                    sale_info=SaleInfo(common_price_rur=90.0, sale_percent="10"),
                )
            ],
            has_next_page=False,
        )
        client = _client(raw)

        products = await client.products.list()

        self.assertEqual(products[0].id, 1)
        self.assertEqual(products[0].price, 100.0)
        self.assertEqual(products[0].sale_price, 90.0)
        self.assertTrue(products[0].visible)

    async def test_product_get_uses_the_identity_map(self):
        raw = _FakeRaw()
        raw.products.data_response = ProductDataResponse(
            product=ProductData(id=1, name="A", price=10.0, currency="USD")
        )
        client = _client(raw)

        first = await client.products.get(1)
        second = await client.products.get(1)
        await client.products.get(1, force_refresh=True)

        self.assertIs(first, second)
        self.assertEqual(raw.products.get_calls, 2)

    async def test_update_price_posts_documented_body(self):
        raw = _FakeRaw()
        raw.products.price_response = PriceUpdateResponse(taskId="job-7")
        client = _client(raw)

        task_id = await client.products.update_price(
            1, 50, variants=[{"variant_id": 2, "rate": 1.5}]
        )

        self.assertEqual(task_id, "job-7")
        self.assertEqual(
            raw.products.price_updates,
            [[{"product_id": 1, "price": 50, "variants": [{"variant_id": 2, "rate": 1.5}]}]],
        )

    async def test_task_status_accepts_a_string_task_id(self):
        raw = _FakeRaw()
        raw.products.task_response = TaskStatusResponse(
            TaskId="job-7", Status=3, SuccessCount=1, TotalCount=1
        )
        client = _client(raw)

        status = await client.products.task_status("job-7")

        self.assertEqual(status.task_id, "job-7")
        self.assertEqual(status.status, 3)
        self.assertEqual(status.success_count, 1)

    async def test_sales_and_purchases_are_mapped(self):
        raw = _FakeRaw()
        raw.sales.sales = [_sale(5)]
        raw.sales.purchase_response = PurchaseInfoResponse(
            content=PurchaseContent(
                content_id=5,
                item_id=9,
                name="Item",
                amount=10.0,
                currency_type="RUB",
                invoice_state=3,
                profit=2.0,
                buyer_info=PurchaseBuyerInfo(email="buyer@example.com"),
                options=[PurchaseOption(id=1, name="login", user_data="user")],
            )
        )
        client = _client(raw)

        sales = await client.sales.last()
        purchase = await client.sales.get(5)

        self.assertEqual(sales[0].invoice_id, 5)
        self.assertEqual(sales[0].product_name, "Item")
        self.assertIs(sales[0]._client, client)
        self.assertEqual(purchase.state_name, "paid")
        self.assertEqual(purchase.buyer_email, "buyer@example.com")
        self.assertEqual(purchase.options[0]["name"], "login")

    async def test_purchase_by_unique_code_is_mapped(self):
        raw = _FakeRaw()
        raw.sales.unique_response = UniqueCodeResponse(
            inv=8,
            id_goods=9,
            amount=10.0,
            type_curr="USD",
            name_invoice="Item",
            email="buyer@example.com",
        )
        client = _client(raw)

        purchase = await client.sales.get_by_unique_code("code")

        self.assertEqual(purchase.invoice_id, 8)
        self.assertEqual(purchase.currency, "USD")

    async def test_reviews_are_paginated(self):
        raw = _FakeRaw()
        raw.reviews.pages = {
            1: ReviewsResponse(total_pages=2, reviews=[_review(1)]),
            2: ReviewsResponse(total_pages=2, reviews=[_review(2)]),
        }
        client = _client(raw)

        reviews = await client.reviews.list(limit=2)

        self.assertEqual([review.id for review in reviews], [1, 2])
        self.assertEqual(reviews[0].product_id, 9)

    async def test_categories_and_balance_are_decoded(self):
        raw = _FakeRaw()
        raw.categories.pages = {
            1: CategoriesResponse(category=[CategorySchema(id=1, name="Games", sub=[2, 3], cnt=10)])
        }
        raw.account.balance_response = BalanceResponse(
            content=BalanceContent(amount_t_free=1.0, amount_t_lock=2.0, amount_t_plus=3.0)
        )
        raw.account.receipts_response = ReceiptsResponse(
            content=ReceiptsContent(
                page=1,
                count=100,
                total_count=1,
                total_pages=1,
                items=[
                    ReceiptItem(
                        account_operation_id=10,
                        operation=ReceiptOperation(
                            id=1, type="sale", price=5.0, currency="RUB", on_account=4.5
                        ),
                        product=ReceiptProduct(
                            id=9,
                            name=[
                                {"locale": "en-US", "value": "Item"},
                                {"locale": "ru-RU", "value": "Товар"},
                            ],
                        ),
                    )
                ],
            )
        )
        client = _client(raw)

        categories = await client.categories.list()
        balance = await client.account.balance()
        receipts = await client.account.receipts()

        self.assertEqual(categories[0].sub_ids, [2, 3])
        self.assertEqual((balance.free, balance.locked, balance.plus), (1.0, 2.0, 3.0))
        self.assertEqual(receipts.items[0].product_name, "Товар")
        self.assertEqual(receipts.items[0].price, 5.0)


class _ListenerTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_tick_baselines_and_emits_only_initial_chats(self):
        raw = _FakeRaw()
        raw.chats.items = [_chat_item()]
        raw.chats.history_rows = [_row(10, buyer=1), _row(11, seller=1)]
        raw.sales.sales = [_sale(1)]
        raw.reviews.pages = {1: ReviewsResponse(reviews=[_review(3)])}
        client = _client(raw)
        listener = EventListener(client, state=MemoryStateStore())

        events = await listener.tick()

        self.assertEqual([event.type for event in events], [GGselEvents.INITIAL_CHAT])
        self.assertEqual(events[0].chat.id, 7)
        self.assertEqual(listener._chats[7].last_id, 11)

    async def test_follow_up_tick_reports_only_new_items(self):
        raw = _FakeRaw()
        raw.chats.items = [_chat_item()]
        raw.chats.history_rows = [_row(10, buyer=1), _row(11, seller=1)]
        raw.sales.sales = [_sale(1)]
        raw.reviews.pages = {1: ReviewsResponse(reviews=[_review(3)])}
        client = _client(raw)
        listener = EventListener(client, state=MemoryStateStore())
        await listener.tick()

        raw.chats.items = [
            _chat_item(last_message=_now() + timedelta(seconds=5), cnt_msg=3, cnt_new=1)
        ]
        raw.chats.history_rows += [_row(12, buyer=1, text="buy"), _row(13, seller=1)]
        raw.sales.sales.append(_sale(2))
        raw.reviews.pages = {1: ReviewsResponse(reviews=[_review(3), _review(4)])}

        events = await listener.tick()

        self.assertEqual(
            [event.type for event in events],
            [GGselEvents.NEW_MESSAGE, GGselEvents.NEW_SALE, GGselEvents.NEW_REVIEW],
        )
        self.assertEqual(events[0].message.id, 12)
        self.assertEqual(events[0].chat.id, 7)
        self.assertEqual(events[1].sale.invoice_id, 2)
        self.assertEqual(events[2].review.id, 4)

    async def test_restart_resumes_state_without_replaying(self):
        store = MemoryStateStore()
        raw = _FakeRaw()
        raw.chats.items = [_chat_item()]
        raw.chats.history_rows = [_row(10, buyer=1)]
        raw.sales.sales = [_sale(1)]
        raw.reviews.pages = {1: ReviewsResponse(reviews=[_review(3)])}
        await EventListener(_client(raw, store=store), state=store).tick()

        restarted_raw = _FakeRaw()
        restarted_raw.chats.items = [_chat_item()]
        restarted_raw.chats.history_rows = [_row(10, buyer=1)]
        restarted_raw.sales.sales = [_sale(1)]
        restarted_raw.reviews.pages = {1: ReviewsResponse(reviews=[_review(3)])}
        restarted = EventListener(_client(restarted_raw, store=store), state=store)

        self.assertEqual(await restarted.tick(), [])

        restarted_raw.sales.sales.append(_sale(2))
        events = await restarted.tick()

        self.assertEqual([event.type for event in events], [GGselEvents.NEW_SALE])
        self.assertEqual(events[0].sale.invoice_id, 2)

    async def test_malformed_state_falls_back_to_a_fresh_start(self):
        store = MemoryStateStore()
        await store.set("ggsel:42:listener", {"version": 1, "chats": "broken"})
        raw = _FakeRaw()
        raw.chats.items = [_chat_item()]
        raw.chats.history_rows = [_row(10, buyer=1)]

        events = await EventListener(_client(raw, store=store), state=store).tick()

        self.assertEqual([event.type for event in events], [GGselEvents.INITIAL_CHAT])

    async def test_a_broken_chat_does_not_hide_other_chats(self):
        raw = _FakeRaw()
        raw.chats.items = [_chat_item(chat_id=1), _chat_item(chat_id=2)]
        raw.chats.fail_chats = {2}
        raw.chats.history_rows = [_row(20, buyer=1)]
        client = _client(raw)
        listener = EventListener(client, state=MemoryStateStore())

        first = await listener.tick()
        self.assertEqual([event.chat.id for event in first], [1])

        second = await listener.tick()
        self.assertEqual(second, [])

        raw.chats.fail_chats.clear()
        third = await listener.tick()
        self.assertEqual(
            [event.type for event in third],
            [GGselEvents.INITIAL_CHAT, GGselEvents.NEW_MESSAGE],
        )
        self.assertEqual(third[0].chat.id, 2)
        self.assertEqual(third[1].message.id, 20)

    async def test_tick_requires_a_started_client(self):
        client = GGsel(GGselClientConfig(api_key="key", seller_id=42))
        with self.assertRaises(RuntimeError):
            await EventListener(client).tick()


def _message_event(client, chat, text="hi"):
    return NewMessageEvent(
        client=client,
        chat=chat,
        message=ChatMessage(id=1, text=text, direction=MessageDirection.BUYER),
    )


class _DispatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_chat_and_text_filters(self):
        client = GGsel(GGselClientConfig(api_key="key", seller_id=42, handler_timeout=0.05))
        seen = []

        @client.on_message
        async def everything(event):
            seen.append(event.message.text)

        @client.on_message(text="exact")
        async def exact(event):
            seen.append(f"exact:{event.message.text}")

        chat = Chat(id=1)
        await client._dispatch(InitialChatEvent(client=client, chat=chat))
        self.assertEqual(seen, [])

        await client._dispatch(_message_event(client, chat, "exact"))
        self.assertEqual(seen, ["exact", "exact:exact"])

        seen.clear()
        await client._dispatch(_message_event(client, chat, "other"))
        self.assertEqual(seen, ["other"])

    async def test_slow_handler_times_out_without_blocking_others(self):
        client = GGsel(GGselClientConfig(api_key="key", seller_id=42, handler_timeout=0.01))
        done = []

        @client.on_new_sale
        async def slow(event):
            await asyncio.sleep(1)
            done.append("slow")

        @client.on_new_sale
        async def fast(event):
            done.append("fast")

        await client._dispatch(NewSaleEvent(client=client, sale=Sale(invoice_id=1)))

        self.assertEqual(done, ["fast"])

    async def test_handler_errors_do_not_escape(self):
        client = GGsel(GGselClientConfig(api_key="key", seller_id=42))

        @client.on_new_review
        async def broken(event):
            raise RuntimeError("boom")

        await client._dispatch(NewReviewEvent(client=client, review=Review(id=1, text="ok")))
