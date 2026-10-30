from __future__ import annotations

from typing import Any

from .basic import ApiModel, GGselDateTime, RetvalResponse


class LoginResponse(ApiModel):
    retval: int | None = None
    desc: str | None = None
    token: str | None = None
    seller_id: int | None = None
    valid_thru: GGselDateTime | None = None


class BalanceContent(ApiModel):
    amount_t_lock: float | None = None
    amount_t_free: float | None = None
    amount_t_plus: float | None = None


class BalanceResponse(RetvalResponse):
    content: BalanceContent | None = None


class ReceiptOperation(ApiModel):
    id: int | None = None
    type: str | None = None
    datetime: GGselDateTime | None = None
    percent: int | None = None
    price: float | None = None
    currency: str | None = None
    on_account: float | None = None


class ReceiptProduct(ApiModel):
    id: int | None = None
    name: Any | None = None
    deleted: bool | None = None


class ReceiptItem(ApiModel):
    account_operation_id: int | None = None
    operation: ReceiptOperation | None = None
    owner_id: int | None = None
    product: ReceiptProduct | None = None
    code_check_datetime: GGselDateTime | None = None
    date_free: GGselDateTime | None = None
    free_description: str | None = None
    response: str | None = None


class ReceiptsContent(ApiModel):
    page: int | None = None
    count: int | None = None
    has_next_page: bool | None = None
    has_previous_page: bool | None = None
    total_count: int | None = None
    total_pages: int | None = None
    items: list[ReceiptItem] = []


class ReceiptsResponse(RetvalResponse):
    content: ReceiptsContent | None = None
