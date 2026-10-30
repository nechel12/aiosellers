import unittest
from types import SimpleNamespace

from aiosellers.playerok import Playerok
from aiosellers.playerok.api.chats import ChatAPI
from aiosellers.playerok.api.items import ItemAPI
from aiosellers.playerok.core.exceptions import MessageNotDeliveredError
from aiosellers.playerok.core.identity_map import IdentityMap
from aiosellers.playerok.entities.item import MyItem
from aiosellers.playerok.schemas import PriorityTypes
from aiosellers.playerok.schemas.items import Item as ItemSchema
from aiosellers.playerok.schemas.items import ItemPriorityStatus
from aiosellers.playerok.schemas.items import MyItem as MyItemSchema


class _Client:
    _use_identity_map = True
    _me_id = "me"

    def __init__(self, raw=None):
        self._identity_maps = SimpleNamespace(items=IdentityMap())
        self._raw = raw

    def _require_raw(self):
        if self._raw is None:
            raise RuntimeError("Client is not started. Call start() or start_polling() first.")
        return self._raw


class _RawItems:
    def __init__(self, schema):
        self.schema = schema
        self.calls = 0

    async def get_item(self, id=None, slug=None):
        self.calls += 1
        return self.schema


def _item(**overrides):
    data = {"id": "i1", "name": "old", "price": 1}
    data.update(overrides)
    return ItemSchema.model_validate(data)


class ItemIdentityTests(unittest.TestCase):
    def test_cached_item_is_updated_in_place(self):
        api = ItemAPI(_Client())
        first = api._create_item(_item())
        second = api._create_item(_item(name="new", price=2))
        self.assertIs(first, second)
        self.assertEqual(first.name, "new")
        self.assertEqual(first.price, 2)

    def test_create_my_item_upgrades_cached_base_item(self):
        api = ItemAPI(_Client())
        base = api._create_item(_item())
        mine = api._create_my_item(_item(name="mine"))
        self.assertIsNot(base, mine)
        self.assertIsInstance(mine, MyItem)
        self.assertTrue(hasattr(mine, "update"))
        self.assertIs(api._client._identity_maps.items.get("i1"), mine)

    def test_create_my_item_updates_existing_my_item(self):
        api = ItemAPI(_Client())
        first = api._create_my_item(_item())
        second = api._create_my_item(
            MyItemSchema.model_validate(
                {"id": "i1", "name": "new", "price": 2, "prevPrice": 1, "isEditable": True}
            )
        )
        self.assertIs(first, second)
        self.assertEqual(second.name, "new")
        self.assertEqual(second.price, 2)
        self.assertEqual(second.prev_price, 1)
        self.assertTrue(second.is_editable)

    def test_unknown_schema_type_builds_my_item(self):
        api = ItemAPI(_Client())
        mine = api._create_my_item(SimpleNamespace(id="i2", name="generic", price=10))
        self.assertIsInstance(mine, MyItem)
        self.assertEqual(mine.name, "generic")
        self.assertEqual(mine.price, 10)

    def test_missing_id_raises_clear_error(self):
        api = ItemAPI(_Client())
        with self.assertRaisesRegex(ValueError, "id"):
            api._create_item(SimpleNamespace())


class _RawPriorityItems:
    def __init__(self, statuses, schema):
        self.statuses = statuses
        self.schema = schema
        self.published: list[str] = []
        self.increased: list[str] = []

    async def get_item(self, id=None, slug=None):
        return self.schema

    async def get_item_priority_statuses(self, item_id, price):
        return list(self.statuses)

    async def publish_item(self, *, item_id, priority_status_id):
        self.published.append(priority_status_id)
        return self.schema

    async def increase_item_priority_status(self, *, item_id, priority_status_id):
        self.increased.append(priority_status_id)
        return self.schema


def _priority(status_id: str, kind: PriorityTypes) -> ItemPriorityStatus:
    return ItemPriorityStatus.model_validate(
        {
            "id": status_id,
            "price": 10,
            "name": status_id,
            "type": kind.value,
            "period": 3600,
            "priceRange": {"min": None, "max": None},
        }
    )


class PlayerokAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_force_refresh_updates_cached_item(self):
        raw_items = _RawItems(_item())
        client = _Client(SimpleNamespace(items=raw_items))
        api = ItemAPI(client)

        first = await api.get("i1")
        raw_items.schema = _item(name="new", price=2)
        refreshed = await api.get("i1", force_refresh=True)

        self.assertIs(first, refreshed)
        self.assertEqual(refreshed.name, "new")
        self.assertEqual(refreshed.price, 2)
        self.assertEqual(raw_items.calls, 2)

    async def test_priority_methods_select_by_type_not_order(self):
        statuses = [
            _priority("prem", PriorityTypes.PREMIUM),
            _priority("norm", PriorityTypes.DEFAULT),
        ]
        raw_items = _RawPriorityItems(statuses, _item())
        client = _Client(SimpleNamespace(items=raw_items))
        api = ItemAPI(client)

        await api.publish("i1")
        await api.publish("i1", premium=True)
        await api.set_normal_priority("i1")
        await api.set_premium_priority("i1")

        self.assertEqual(raw_items.published, ["norm", "prem"])
        self.assertEqual(raw_items.increased, ["norm", "prem"])

    async def test_priority_method_raises_when_type_is_missing(self):
        statuses = [_priority("prem", PriorityTypes.PREMIUM)]
        raw_items = _RawPriorityItems(statuses, _item())
        api = ItemAPI(_Client(SimpleNamespace(items=raw_items)))

        with self.assertRaisesRegex(ValueError, "default priority"):
            await api.publish("i1")
        with self.assertRaisesRegex(ValueError, "default priority"):
            await api.set_normal_priority("i1")
        self.assertEqual(raw_items.published, [])
        self.assertEqual(raw_items.increased, [])

    async def test_account_api_before_start_raises_clear_error(self):
        client = Playerok("token")
        with self.assertRaisesRegex(RuntimeError, "not started"):
            await client.account.me()

    async def test_send_message_without_payload_raises(self):
        class _RawChats:
            async def send_message(self, **kwargs):
                return None

        class _ChatClient:
            _me_id = "me"

            def _require_raw(self):
                return SimpleNamespace(chats=_RawChats())

        api = ChatAPI(_ChatClient())
        with self.assertRaises(MessageNotDeliveredError):
            await api.send_message("c1", text="hi")
