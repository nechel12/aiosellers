from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator

from ..core.types import ImageInput
from ..entities.game import GameCategoryDataField, GameCategoryOption
from ..entities.item import Item, MyItem
from ..schemas import ItemsSortOptions, PriorityTypes

if TYPE_CHECKING:
    from ..playerok import Playerok


class ItemAPI:
    def __init__(self, client: Playerok) -> None:
        self._client = client

    @staticmethod
    def _schema_value(schema, *names, default=None):
        for name in names:
            if hasattr(schema, name):
                return getattr(schema, name)
        return default

    @classmethod
    def _base_values(cls, schema) -> dict:
        user = cls._schema_value(schema, "user")
        return {
            "id": schema.id,
            "slug": cls._schema_value(schema, "slug"),
            "name": cls._schema_value(schema, "name"),
            "description": cls._schema_value(schema, "description"),
            "price": cls._schema_value(schema, "price"),
            "status": cls._schema_value(schema, "status"),
            "priority": cls._schema_value(schema, "priority"),
            "game_id": cls._schema_value(schema, "game_id"),
            "category_id": cls._schema_value(schema, "category_id"),
            "obtaining_type_id": cls._schema_value(schema, "obtaining_type_id"),
            "user_id": getattr(user, "id", None) if user is not None else None,
        }

    @classmethod
    def _my_values(cls, schema) -> dict:
        return {
            "prev_price": cls._schema_value(schema, "prev_price", "raw_price"),
            "priority_price": cls._schema_value(schema, "priority_price"),
            "priority_position": cls._schema_value(schema, "priority_position"),
            "is_editable": cls._schema_value(schema, "is_editable"),
            "buyer": cls._schema_value(schema, "buyer"),
        }

    @classmethod
    def _apply_schema(cls, item: Item, schema) -> None:
        for name, value in cls._base_values(schema).items():
            if value is not None:
                setattr(item, name, value)

        if not isinstance(item, MyItem):
            return
        if hasattr(schema, "prev_price") and schema.prev_price is not None:
            item.prev_price = schema.prev_price
        elif hasattr(schema, "raw_price") and schema.raw_price is not None:
            item.prev_price = schema.raw_price
        for name in ("priority_price", "priority_position", "is_editable", "buyer"):
            value = getattr(schema, name, None)
            if value is not None:
                setattr(item, name, value)

    def _create_item(self, schema) -> Item:
        item_id = self._schema_value(schema, "id")
        if not item_id:
            raise ValueError("Item schema does not contain an id")

        if self._client._use_identity_map:
            cached = self._client._identity_maps.items.get(item_id)
            if cached is not None:
                self._apply_schema(cached, schema)
                return cached

        item = Item(**self._base_values(schema))
        item._client = self._client

        if self._client._use_identity_map:
            self._client._identity_maps.items.set(item.id, item)

        return item

    def _create_my_item(self, schema) -> MyItem:
        item_id = self._schema_value(schema, "id")
        if not item_id:
            raise ValueError("Item schema does not contain an id")

        if self._client._use_identity_map:
            cached = self._client._identity_maps.items.get(item_id)
            if isinstance(cached, MyItem):
                self._apply_schema(cached, schema)
                return cached

        item = MyItem(**self._base_values(schema), **self._my_values(schema))
        item._client = self._client

        if self._client._use_identity_map:
            self._client._identity_maps.items.set(item.id, item)

        return item

    def _extract_options(
        self, options: dict[str, str] | list[GameCategoryOption] | None
    ) -> dict[str, str] | None:
        if options is None:
            return None
        if isinstance(options, dict):
            return options
        result = {}
        for opt in options:
            if hasattr(opt, "_input_value") and opt._input_value is not None:
                result[opt.slug] = str(opt._input_value)
        return result if result else None

    def _extract_data_fields(
        self, data_fields: dict[str, str] | list[GameCategoryDataField] | None
    ) -> dict[str, str] | None:
        if data_fields is None:
            return None
        if isinstance(data_fields, dict):
            return data_fields
        result = {}
        for field in data_fields:
            if hasattr(field, "_input_value") and field._input_value is not None:
                result[field.id] = field._input_value
        return result if result else None

    async def _get_priority_statuses(self, item_id: str, price: int):
        return await self._client._require_raw().items.get_item_priority_statuses(item_id, price)

    @staticmethod
    def _priority_by_type(statuses, priority_type: PriorityTypes):
        return next((status for status in statuses if status.type == priority_type), None)

    async def get(
        self, id: str | None = None, *, slug: str | None = None, force_refresh: bool = False
    ) -> Item | None:
        if id and not force_refresh and self._client._use_identity_map:
            cached = self._client._identity_maps.items.get(id)
            if cached:
                return cached

        schema = await self._client._require_raw().items.get_item(id, slug)
        if schema is None:
            return None

        return self._create_item(schema)

    async def list(
        self,
        *,
        limit: int = 24,
        cursor: str | None = None,
        game_id: str | None = None,
        category_id: str | None = None,
        user_id: str | None = None,
        minimal_price: int | None = None,
        maximal_price: int | None = None,
        has_discount: bool | None = None,
        has_reviews: bool | None = None,
        attributes: list[dict[str, str]] | None = None,
        search: str | None = None,
        sort: ItemsSortOptions | None = None,
    ) -> list[Item]:
        result = []
        remain = limit
        current_cursor = cursor

        while remain > 0:
            response = await self._client._require_raw().items.get_items(
                count=min(24, remain),
                cursor=current_cursor,
                game_id=game_id,
                user_id=user_id,
                category_id=category_id,
                minimal_price=minimal_price,
                maximal_price=maximal_price,
                has_discount=has_discount,
                has_reviews=has_reviews,
                attributes=attributes,
                search=search,
                sort=sort,
            )
            if response is None or not response.items:
                break

            for schema in response.items:
                result.append(self._create_item(schema))

            remain -= len(response.items)

            if not response.page_info.has_next_page:
                break
            current_cursor = response.page_info.end_cursor

        return result[:limit]

    async def iter(
        self,
        *,
        cursor: str | None = None,
        game_id: str | None = None,
        category_id: str | None = None,
        user_id: str | None = None,
        minimal_price: int | None = None,
        maximal_price: int | None = None,
        has_discount: bool | None = None,
        has_reviews: bool | None = None,
        attributes: list[dict[str, str]] | None = None,
        search: str | None = None,
        sort: ItemsSortOptions | None = None,
    ) -> AsyncIterator[Item]:
        current_cursor = cursor

        while True:
            response = await self._client._require_raw().items.get_items(
                cursor=current_cursor,
                game_id=game_id,
                user_id=user_id,
                category_id=category_id,
                minimal_price=minimal_price,
                maximal_price=maximal_price,
                has_discount=has_discount,
                has_reviews=has_reviews,
                attributes=attributes,
                search=search,
                sort=sort,
            )
            if response is None or not response.items:
                return

            for schema in response.items:
                yield self._create_item(schema)

            if not response.page_info.has_next_page:
                break
            current_cursor = response.page_info.end_cursor

    async def list_self(self, *, limit: int = 24, cursor: str | None = None) -> list[MyItem]:
        result = []
        remain = limit
        current_cursor = cursor

        while remain > 0:
            response = await self._client._require_raw().items.get_items(
                count=min(24, remain),
                cursor=current_cursor,
                user_id=self._client._me_id,
            )
            if response is None or not response.items:
                break

            for schema in response.items:
                result.append(self._create_my_item(schema))

            remain -= len(response.items)

            if not response.page_info.has_next_page:
                break
            current_cursor = response.page_info.end_cursor

        return result[:limit]

    async def iter_self(self, *, cursor: str | None = None) -> AsyncIterator[MyItem]:
        current_cursor = cursor

        while True:
            response = await self._client._require_raw().items.get_items(
                cursor=current_cursor,
                user_id=self._client._me_id,
            )
            if response is None or not response.items:
                return

            for schema in response.items:
                yield self._create_my_item(schema)

            if not response.page_info.has_next_page:
                break
            current_cursor = response.page_info.end_cursor

    async def create(
        self,
        *,
        category: str | object,
        obtaining_type: str | object,
        name: str,
        price: int,
        description: str,
        options: dict[str, str] | list[GameCategoryOption] | None = None,
        data_fields: dict[str, str] | list[GameCategoryDataField] | None = None,
        attachments: list[ImageInput] | None = None,
    ) -> MyItem | None:
        category_id = category.id if hasattr(category, "id") else category
        obtaining_type_id = obtaining_type.id if hasattr(obtaining_type, "id") else obtaining_type

        # Extract options and data_fields
        options_dict = self._extract_options(options)
        data_fields_dict = self._extract_data_fields(data_fields)

        schema = await self._client._require_raw().items.create_item(
            game_category_id=category_id,
            obtaining_type_id=obtaining_type_id,
            name=name,
            price=price,
            description=description,
            options=options_dict or {},
            data_fields=data_fields_dict or {},
            attachments=attachments or [],
        )
        if schema is None:
            return None

        return self._create_my_item(schema)

    async def update(
        self,
        item_id: str,
        *,
        name: str | None = None,
        price: int | None = None,
        description: str | None = None,
        options: dict[str, str] | list[GameCategoryOption] | None = None,
        data_fields: dict[str, str] | list[GameCategoryDataField] | None = None,
        remove_attachments: list[str] | None = None,
        add_attachments: list[ImageInput] | None = None,
    ) -> MyItem | None:
        options_dict = self._extract_options(options)
        data_fields_dict = self._extract_data_fields(data_fields)

        schema = await self._client._require_raw().items.update_item(
            id=item_id,
            name=name,
            price=price,
            description=description,
            options=options_dict,
            data_fields=data_fields_dict,
            remove_attachments=remove_attachments,
            add_attachments=add_attachments,
        )
        if schema is None:
            return None

        return self._create_my_item(schema)

    async def remove(self, item_id: str) -> bool:
        return await self._client._require_raw().items.remove_item(item_id)

    async def publish(self, item_id: str, *, premium: bool = False) -> MyItem | None:
        item = await self.get(item_id)
        if item is None or item.price is None:
            raise ValueError(f"Item {item_id} not found or price is missing")

        statuses = await self._get_priority_statuses(item_id, item.price)

        wanted = PriorityTypes.PREMIUM if premium else PriorityTypes.DEFAULT
        priority_status = self._priority_by_type(statuses, wanted)
        if priority_status is None:
            raise ValueError(f"No {wanted.value.lower()} priority available for this item")

        schema = await self._client._require_raw().items.publish_item(
            item_id=item_id,
            priority_status_id=priority_status.id,
        )
        if schema is None:
            return None

        return self._create_my_item(schema)

    async def set_normal_priority(self, item_id: str) -> MyItem | None:
        item = await self.get(item_id)
        if item is None or item.price is None:
            raise ValueError(f"Item {item_id} not found or price is missing")

        statuses = await self._get_priority_statuses(item_id, item.price)

        priority_status = self._priority_by_type(statuses, PriorityTypes.DEFAULT)
        if priority_status is None:
            raise ValueError("No default priority available for this item")

        schema = await self._client._require_raw().items.increase_item_priority_status(
            item_id=item_id,
            priority_status_id=priority_status.id,
        )
        if schema is None:
            return None

        return self._create_my_item(schema)

    async def set_premium_priority(self, item_id: str) -> MyItem | None:
        item = await self.get(item_id)
        if item is None or item.price is None:
            raise ValueError(f"Item {item_id} not found or price is missing")

        statuses = await self._get_priority_statuses(item_id, item.price)

        priority_status = self._priority_by_type(statuses, PriorityTypes.PREMIUM)
        if priority_status is None:
            raise ValueError("No premium priority available for this item")

        schema = await self._client._require_raw().items.increase_item_priority_status(
            item_id=item_id,
            priority_status_id=priority_status.id,
        )
        if schema is None:
            return None

        return self._create_my_item(schema)
