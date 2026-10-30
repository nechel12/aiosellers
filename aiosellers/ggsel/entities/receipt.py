from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..schemas import ReceiptItem as ReceiptSchema


def _localized_name(name: Any) -> str | None:
    if isinstance(name, str):
        return name or None
    if not isinstance(name, list):
        return None
    values: dict[str, str] = {}
    for entry in name:
        if not isinstance(entry, dict):
            continue
        locale = entry.get("locale")
        value = entry.get("value")
        if isinstance(locale, str) and isinstance(value, str):
            values[locale] = value
    for locale in ("ru-RU", "ru", "en-US", "en"):
        if values.get(locale):
            return values[locale]
    return next((value for value in values.values() if value), None)


@dataclass(slots=True, frozen=True)
class Receipt:
    id: int | None = None
    operation_id: int | None = None
    operation_type: str | None = None
    date: datetime | None = None
    percent: int | None = None
    price: float | None = None
    currency: str | None = None
    on_account: float | None = None
    owner_id: int | None = None
    product_id: int | None = None
    product_name: str | None = None
    code_check_datetime: datetime | None = None
    date_free: datetime | None = None
    free_description: str | None = None
    response: str | None = None

    @classmethod
    def from_schema(cls, schema: ReceiptSchema) -> Receipt:
        operation = schema.operation
        product = schema.product
        product_name = _localized_name(product.name) if product is not None else None
        return cls(
            id=schema.account_operation_id,
            operation_id=operation.id if operation is not None else None,
            operation_type=operation.type if operation is not None else None,
            date=operation.datetime if operation is not None else None,
            percent=operation.percent if operation is not None else None,
            price=operation.price if operation is not None else None,
            currency=operation.currency if operation is not None else None,
            on_account=operation.on_account if operation is not None else None,
            owner_id=schema.owner_id,
            product_id=product.id if product is not None else None,
            product_name=product_name,
            code_check_datetime=schema.code_check_datetime,
            date_free=schema.date_free,
            free_description=schema.free_description,
            response=schema.response,
        )


@dataclass(slots=True, frozen=True)
class ReceiptPage:
    page: int | None = None
    count: int | None = None
    total_count: int | None = None
    total_pages: int | None = None
    has_next_page: bool | None = None
    items: list[Receipt] = field(default_factory=list)
