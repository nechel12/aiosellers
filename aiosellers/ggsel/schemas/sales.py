from __future__ import annotations

from typing import Any

from .basic import ApiModel, GGselDateTime, RetvalResponse


class SaleProduct(ApiModel):
    id: int | None = None
    name: str | None = None
    price_rub: float | None = None
    price_usd: float | None = None
    price_eur: float | None = None
    price_uah: float | None = None


class SaleSchema(ApiModel):
    invoice_id: int
    date: GGselDateTime | None = None
    product: SaleProduct | None = None


class LastSalesResponse(RetvalResponse):
    sales: list[SaleSchema] = []


class PurchaseFeedback(ApiModel):
    deleted: int | None = None
    feedback: str | None = None
    feedback_type: str | None = None
    comment: str | None = None


class PurchaseBuyerInfo(ApiModel):
    payment_method: str | None = None
    account: str | None = None
    email: str | None = None
    phone: str | None = None
    skype: str | None = None
    whatsapp: str | None = None
    ip_address: str | None = None
    payment_aggregator: str | None = None


class PurchaseOption(ApiModel):
    id: int | None = None
    name: str | None = None
    user_data: str | None = None
    user_data_id: int | None = None


class PurchaseContent(ApiModel):
    content_id: int | None = None
    item_id: int | None = None
    cart_uid: str | None = None
    name: str | None = None
    amount: float | None = None
    currency_type: str | None = None
    invoice_state: int | None = None
    purchase_date: GGselDateTime | None = None
    date_pay: GGselDateTime | None = None
    agent_id: int | None = None
    agent_percent: float | None = None
    agent_fee: float | None = None
    query_string: str | None = None
    unit_goods: str | None = None
    cnt_goods: str | None = None
    promo_code: str | None = None
    bonus_code: str | None = None
    feedback: PurchaseFeedback | None = None
    unique_code_state: Any | None = None
    options: list[PurchaseOption] = []
    buyer_info: PurchaseBuyerInfo | None = None
    owner: int | None = None
    day_lock: int | None = None
    lock_state: int | None = None
    profit: float | None = None
    external_order_id: str | None = None


class PurchaseInfoResponse(RetvalResponse):
    content: PurchaseContent | None = None


class UniqueCodeResponse(RetvalResponse):
    inv: int | None = None
    id_goods: int | None = None
    amount: float | None = None
    type_curr: str | None = None
    amount_usd: float | None = None
    profit: float | None = None
    date_pay: GGselDateTime | None = None
    email: str | None = None
    name_invoice: str | None = None
    lang: str | None = None
    agent_id: int | None = None
    agent_percent: str | None = None
    query_string: str | None = None
    unit_goods: str | None = None
    cnt_goods: str | None = None
    promo_code: str | None = None
    bonus_code: str | None = None
    cart_uid: str | None = None
    unique_code_state: Any | None = None
    options: list[PurchaseOption] = []
