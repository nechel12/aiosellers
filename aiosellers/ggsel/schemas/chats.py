from __future__ import annotations

from .basic import ApiModel, GGselDateTime, RetvalResponse


class ChatItem(ApiModel):
    id_i: int
    email: str | None = None
    product: int | None = None
    last_message: GGselDateTime | None = None
    cnt_msg: int | None = None
    cnt_new: int | None = None


class ChatList(ApiModel):
    cnt_pages: int | None = None
    items: list[ChatItem] = []


class ChatMessageSchema(ApiModel):
    id: int
    message: str | None = None
    buyer: int = 0
    seller: int = 0
    deleted: int | None = None
    date_written: GGselDateTime | None = None
    date_seen: GGselDateTime | None = None
    is_file: int | None = None
    filename: str | None = None
    url: str | None = None
    is_img: int | None = None
    preview: str | None = None


class SendMessageResponse(RetvalResponse):
    pass
