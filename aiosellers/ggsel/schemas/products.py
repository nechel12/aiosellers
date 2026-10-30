from __future__ import annotations

from typing import Any

from pydantic import Field

from .basic import ApiModel, GGselDateTime, RetvalResponse


class SaleInfo(ApiModel):
    common_base_price: float | None = None
    common_price_usd: float | None = None
    common_price_eur: float | None = None
    common_price_rur: float | None = None
    common_price_uah: float | None = None
    sale_end: GGselDateTime | None = None
    sale_percent: str | float | None = None


class ProductRow(ApiModel):
    id_goods: int
    name_goods: str | None = None
    info_goods: str | None = None
    price: str | None = None
    currency: str | None = None
    add_info: str | None = None
    cnt_sell: int | None = None
    cnt_return: int | None = None
    cnt_goodresponses: int | None = None
    cnt_badresponses: int | None = None
    price_usd: float | None = None
    price_eur: float | None = None
    price_uah: float | None = None
    price_rur: float | None = None
    in_stock: int | None = None
    num_in_stock: int | None = None
    visible: int | None = None
    commiss_agent: str | None = None
    has_discount: bool | None = None
    num_options: int | None = None
    sale_info: SaleInfo | None = None


class ProductListResponse(RetvalResponse):
    page: int | None = None
    count: int | None = None
    has_next_page: bool | None = None
    has_previous_page: bool | None = None
    total_count: int | None = None
    total_pages: int | None = None
    rows: list[ProductRow] = []


class ProductPrices(ApiModel):
    initial: dict[str, float | None] | None = None
    default: dict[str, float | None] | None = None


class ProductStatistics(ApiModel):
    sales: int | None = None
    refunds: int | None = None
    good_reviews: int | None = None
    bad_reviews: int | None = None


class ProductSeller(ApiModel):
    id: int | None = None
    name: str | None = None


class ProductData(ApiModel):
    id: int | None = None
    id_prev: int | None = None
    id_next: int | None = None
    name: str | None = None
    price: float | None = None
    currency: str | None = None
    url: str | None = None
    info: str | None = None
    add_info: str | None = None
    release_date: GGselDateTime | None = None
    agency_fee: str | None = None
    agency_sum: str | None = None
    agency_id: int | None = None
    collection: str | None = None
    is_available: int | None = None
    show_rest: int | None = None
    num_in_stock: int | None = None
    num_in_lock: int | None = None
    prices: ProductPrices | None = None
    category_id: int | None = None
    type: str | None = None
    text: str | None = None
    file: str | None = None
    statistics: ProductStatistics | None = None
    seller: ProductSeller | None = None
    sale_info: SaleInfo | None = None
    options: list[dict[str, Any]] = []
    payment_methods: list[dict[str, Any]] = []


class ProductDataResponse(RetvalResponse):
    product: ProductData | None = None


class SellerGoodsResponse(RetvalResponse):
    id_seller: int | None = None
    name_seller: str | None = None
    cnt_goods: int | None = None
    pages: int | None = None
    page: int | None = None
    order_col: str | None = None
    order_dir: str | None = None
    rows: list[ProductRow] = []


class PriceVariant(ApiModel):
    variant_id: int
    rate: float | None = None
    type: str | None = None


class PriceUpdateItem(ApiModel):
    product_id: int
    price: float
    variants: list[PriceVariant] = Field(default_factory=list)


class PriceUpdateResponse(ApiModel):
    task_id: str | int | None = Field(None, alias="taskId")


class TaskErrorDescription(ApiModel):
    key: str | None = Field(None, alias="Key")
    value: str | None = Field(None, alias="Value")


class TaskStatusResponse(ApiModel):
    task_id: str | int | None = Field(None, alias="TaskId")
    status: int | None = Field(None, alias="Status")
    success_count: int | None = Field(None, alias="SuccessCount")
    error_count: int | None = Field(None, alias="ErrorCount")
    total_count: int | None = Field(None, alias="TotalCount")
    errors: list[TaskErrorDescription] = Field(default_factory=list, alias="ErrorsDescriptions")
