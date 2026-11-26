from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from ..core.exceptions import RequestFailedError
from ..schemas import ChatItem, ChatList, ChatMessageSchema, SendMessageResponse
from ..transport import GGselTransport

logger = logging.getLogger(__name__)


def _valid_rows[Row: BaseModel](model: type[Row], rows: list[Any]) -> list[Row]:
    result = []
    for index, row in enumerate(rows):
        try:
            result.append(model.model_validate(row))
        except ValidationError:
            logger.warning("Skipping malformed GGsel %s row at index %s", model.__name__, index)
    return result


class RawChatService:
    def __init__(self, transport: GGselTransport):
        self._transport = transport

    async def list_chats(
        self,
        *,
        filter_new: bool | None = None,
        email: str | None = None,
        product_ids: list[int] | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> ChatList:
        params: dict[str, Any] = {}
        if filter_new is not None:
            params["filter_new"] = int(filter_new)
        if email:
            params["email"] = email
        if product_ids:
            params["id_ds"] = ",".join(str(product_id) for product_id in product_ids)
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["pagesize"] = page_size

        data = await self._transport.request(
            "get", "/api_sellers/api/debates/v2/chats", params=params
        )
        payload = data if isinstance(data, dict) else {}
        items = payload.get("items")
        if isinstance(items, list):
            payload = {**payload, "items": _valid_rows(ChatItem, items)}
        return ChatList.model_validate(payload)

    async def history(
        self,
        chat_id: int | str,
        *,
        from_id: int | None = None,
        to_id: int | None = None,
        newer: bool | None = None,
        count: int | None = None,
    ) -> list[ChatMessageSchema]:
        params: dict[str, Any] = {"id_i": chat_id}
        if from_id is not None:
            params["id_from"] = from_id
        if to_id is not None:
            params["id_to"] = to_id
        if newer is not None:
            params["newer"] = int(newer)
        if count is not None:
            params["count"] = min(100, max(1, count))

        data = await self._transport.request("get", "/api_sellers/api/debates/v2", params=params)
        if not isinstance(data, list):
            raise RequestFailedError("GGsel returned an unexpected chat history payload")
        return _valid_rows(ChatMessageSchema, data)

    async def send_message(self, chat_id: int | str, message: str) -> SendMessageResponse:
        data = await self._transport.request(
            "post",
            "/api_sellers/api/debates/v2",
            params={"id_i": chat_id},
            json_body={"message": message},
            retry=False,
        )
        return SendMessageResponse.model_validate(data if isinstance(data, dict) else {})
