"""A small common API over the three built-in clients."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from math import isfinite
from typing import TYPE_CHECKING

from .capabilities import Capability, Platform, capabilities_for

if TYPE_CHECKING:
    from ..funpay import FunPay
    from ..funpay.entities.chat import Message as FunPayMessage
    from ..funpay.entities.lot import MyLot
    from ..funpay.entities.order import Order
    from ..ggsel import GGsel
    from ..ggsel.entities.chat import ChatMessage as GGselMessage
    from ..ggsel.entities.product import Product
    from ..ggsel.entities.sale import Sale
    from ..playerok import Playerok
    from ..playerok.entities.chat import ChatMessage as PlayerokMessage
    from ..playerok.entities.deal import Deal
    from ..playerok.entities.item import MyItem


def _check_limit(limit: int) -> None:
    if type(limit) is not int or not 0 <= limit <= 100:
        raise ValueError("limit must be an integer between 0 and 100")


class SellerSession:
    """Common operations on an already started built-in client.

    Returned entities keep their platform types. A timeout covers the entire operation,
    including pagination and retry delays.
    """

    def __init__(self, client: FunPay | Playerok | GGsel, *, timeout: float | None = None) -> None:
        if timeout is not None and (not isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be positive and finite")
        self.client = client
        self.platform = Platform(client.platform)
        self.capabilities = capabilities_for(self.platform)
        self.timeout = timeout
        self.messages = SellerMessages(self)
        self.listings = SellerListings(self)
        self.orders = SellerOrders(self)

    def _require(self, any_of: Capability) -> None:
        if not self.capabilities & any_of:
            raise NotImplementedError(f"{self.platform} does not support {any_of}")


class SellerMessages:
    def __init__(self, session: SellerSession) -> None:
        self._session = session

    async def send(self, chat_id: int | str, text: str) -> None:
        """Send only text, without marking the chat read or retrying uncertain writes."""
        from ..ggsel import GGsel
        from ..playerok import Playerok

        self._session._require(Capability.MESSAGES)
        if not text.strip():
            raise ValueError("Message text must not be empty")
        client = self._session.client
        async with asyncio.timeout(self._session.timeout):
            if isinstance(client, GGsel):
                await client.chats.send(chat_id, text)
            elif isinstance(client, Playerok):
                await client.chats.send_message(str(chat_id), text=text)
            else:
                await client.chats.send_message(chat_id, text=text)

    async def list(
        self, chat_id: int | str, *, limit: int = 50
    ) -> Sequence[FunPayMessage | GGselMessage | PlayerokMessage]:
        """Read a bounded window of messages, preserving the adapter's order."""
        from ..ggsel import GGsel
        from ..playerok import Playerok

        self._session._require(Capability.MESSAGES)
        _check_limit(limit)
        if not limit:
            return []
        client = self._session.client
        async with asyncio.timeout(self._session.timeout):
            if isinstance(client, GGsel):
                return await client.chats.history(chat_id, limit=limit)
            if isinstance(client, Playerok):
                return await client.chats.messages.list(str(chat_id), limit=limit)
            return await client.chats.messages.list(chat_id, limit=limit)


class SellerListings:
    def __init__(self, session: SellerSession) -> None:
        self._session = session

    async def list(
        self, *, limit: int = 50, subcategory_id: int | None = None
    ) -> Sequence[MyLot | MyItem | Product]:
        """Read the account's listings; FunPay requires a subcategory."""
        from ..funpay import FunPay
        from ..ggsel import GGsel

        self._session._require(Capability.LIST_MANAGEMENT)
        _check_limit(limit)
        if not limit:
            return []
        client = self._session.client
        async with asyncio.timeout(self._session.timeout):
            if isinstance(client, FunPay):
                if subcategory_id is None:
                    raise ValueError("FunPay listings require subcategory_id")
                return (await client.lots.list_self(subcategory_id))[:limit]
            if subcategory_id is not None:
                raise ValueError("subcategory_id is only supported for FunPay listings")
            if isinstance(client, GGsel):
                return await client.products.my(limit=limit)
            return await client.items.list_self(limit=limit)


class SellerOrders:
    def __init__(self, session: SellerSession) -> None:
        self._session = session

    async def list(self, *, limit: int = 50) -> Sequence[Order | Deal | Sale]:
        """Read recent sales (FunPay/GGsel) or the current account's deals (PlayerOK)."""
        from ..funpay import FunPay
        from ..ggsel import GGsel

        self._session._require(Capability.ORDERS | Capability.DEALS)
        _check_limit(limit)
        if not limit:
            return []
        client = self._session.client
        async with asyncio.timeout(self._session.timeout):
            if isinstance(client, FunPay):
                return [order async for order in client.orders.iter(limit=limit)]
            if isinstance(client, GGsel):
                return (await client.sales.last(top=limit))[:limit]
            return await client.deals.list(limit=limit)
