from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, fields
from typing import Any, cast

from .api import AccountAPI, CategoryAPI, ChatAPI, ProductAPI, ReviewAPI, SaleAPI
from .client_config import GGselClientConfig
from .core.config import GGselConfig
from .core.identity_map import IdentityMap
from .entities.chat import Chat
from .entities.product import Product
from .events import GGselEvent
from .listener import EventListener
from .raw import RawAPI
from .schemas import EventTypes
from .transport import GGselTransport

logger = logging.getLogger("aiosellers.ggsel")

Handler = Callable[[GGselEvent], Awaitable[None]]
Predicate = Callable[[GGselEvent], bool]
TextFilter = str | Callable[[str | None], bool]

_SKIP = {EventTypes.INITIAL_CHAT}


@dataclass(slots=True)
class _Handler:
    event_type: EventTypes
    fn: Handler
    text: TextFilter | None = None
    predicate: Predicate | None = None


@dataclass(slots=True)
class _IdentityMaps:
    chats: IdentityMap[int, Chat]
    products: IdentityMap[int, Product]


class GGsel:
    """High-level GGsel seller client built on the official V1 API."""

    def __init__(self, config: GGselClientConfig | str | None = None) -> None:
        if isinstance(config, str):
            config = GGselClientConfig(api_key=config)
        elif config is None:
            config = GGselClientConfig()

        self._config = config
        self._transport: GGselTransport | None = None
        self._raw: RawAPI | None = None
        self._use_identity_map = config.use_identity_map
        self._seller_id: int | None = config.seller_id
        self._polling_task: asyncio.Task | None = None

        if self._use_identity_map:
            self._identity_maps = _IdentityMaps(
                chats=IdentityMap(),
                products=IdentityMap(),
            )

        self.account = AccountAPI(self)
        self.categories = CategoryAPI(self)
        self.chats = ChatAPI(self)
        self.products = ProductAPI(self)
        self.reviews = ReviewAPI(self)
        self.sales = SaleAPI(self)
        self._handlers: list[_Handler] = []

    @property
    def seller_id(self) -> int | None:
        return self._seller_id

    def _require_raw(self) -> RawAPI:
        if self._raw is None or self._transport is None:
            raise RuntimeError("Client is not started. Call start() or start_polling() first.")
        return self._raw

    def remember(self, bucket: str, key: Any, entity: Any) -> Any:
        entity._client = self
        if not self._use_identity_map:
            return entity
        cache = getattr(self._identity_maps, bucket)
        current = cache.get(key)
        if current is None or type(current) is not type(entity):
            return cache.set(key, entity)
        for item in fields(entity):
            if item.name.startswith("_"):
                continue
            setattr(current, item.name, getattr(entity, item.name))
        return current

    def cached(self, bucket: str, key: Any) -> Any | None:
        if not self._use_identity_map:
            return None
        return getattr(self._identity_maps, bucket).get(key)

    async def __aenter__(self) -> GGsel:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        await self.close()

    async def start(self) -> None:
        if self._transport is not None:
            return

        transport = GGselTransport(
            api_key=self._config.api_key,
            seller_id=self._config.seller_id,
            config=GGselConfig(
                user_agent=self._config.user_agent,
                request_timeout=self._config.request_timeout,
                base_url=self._config.base_url,
                locale=self._config.locale,
            ),
        )
        try:
            await transport.login()
        except BaseException:
            await transport.close()
            raise

        self._transport = transport
        self._raw = RawAPI(transport)
        self._seller_id = transport.seller_id

    async def close(self) -> None:
        transport = self._transport
        self._transport = None
        self._raw = None
        if self._use_identity_map:
            self._identity_maps.chats.clear()
            self._identity_maps.products.clear()
        if transport is not None:
            await transport.close()

    def listen(
        self,
        *,
        messages: bool = True,
        sales: bool = True,
        reviews: bool = True,
        interval: float | None = None,
    ):
        if self._transport is None:
            raise RuntimeError("Client is not started. Call start() or start_polling() first.")
        return EventListener(self, state=self._config.state).listen(
            messages=messages,
            sales=sales,
            reviews=reviews,
            interval=interval,
        )

    async def start_polling(
        self,
        *,
        messages: bool = True,
        sales: bool = True,
        reviews: bool = True,
    ) -> None:
        """Start the session, dispatch decorator handlers, and close on exit."""
        await self.start()
        self._polling_task = asyncio.current_task()
        try:
            async for event in self.listen(messages=messages, sales=sales, reviews=reviews):
                await self._dispatch(event)
        finally:
            self._polling_task = None
            await self.close()

    def stop(self) -> None:
        """Stop the loop started by :meth:`start_polling` from another task."""
        task = self._polling_task
        if task is not None and task is not asyncio.current_task() and not task.done():
            task.cancel()

    def on(
        self,
        event_type: EventTypes,
        fn: Handler | Predicate | None = None,
        *,
        text: TextFilter | None = None,
    ):
        return self._on(event_type, fn, text=text)

    def on_message(self, fn: Handler | Predicate | None = None, *, text: TextFilter | None = None):
        return self._on(EventTypes.NEW_MESSAGE, fn, text=text)

    def on_new_sale(self, fn: Handler | Predicate | None = None, *, text: TextFilter | None = None):
        return self._on(EventTypes.NEW_SALE, fn, text=text)

    def on_new_review(
        self, fn: Handler | Predicate | None = None, *, text: TextFilter | None = None
    ):
        return self._on(EventTypes.NEW_REVIEW, fn, text=text)

    def _on(
        self,
        event_type: EventTypes,
        fn: Handler | Predicate | None = None,
        *,
        text: TextFilter | None = None,
    ):
        def register(func: Handler, predicate: Predicate | None = None) -> Handler:
            self._handlers.append(
                _Handler(event_type=event_type, fn=func, text=text, predicate=predicate)
            )
            return func

        if fn is None:
            return register
        if inspect.iscoroutinefunction(fn):
            return register(cast(Handler, fn))
        return lambda func: register(func, predicate=cast(Predicate, fn))

    async def _dispatch(self, event: GGselEvent) -> None:
        if event.type in _SKIP:
            return
        handlers: list[_Handler] = []
        for handler in list(self._handlers):
            if handler.event_type != event.type:
                continue
            if handler.text is not None:
                message = getattr(event, "message", None)
                text = message.text if message is not None else None
                try:
                    matched = handler.text(text) if callable(handler.text) else text == handler.text
                except Exception:
                    logger.exception("Event text filter failed")
                    continue
                if not matched:
                    continue
            if handler.predicate is not None:
                try:
                    if not handler.predicate(event):
                        continue
                except Exception:
                    logger.exception("Event filter failed")
                    continue
            handlers.append(handler)
        if not handlers:
            return

        timeout = self._config.handler_timeout
        limit = asyncio.Semaphore(max(1, self._config.max_concurrent_handlers))

        async def run(handler: _Handler) -> None:
            async with limit:
                try:
                    coro = handler.fn(event)
                    if timeout is not None and timeout > 0:
                        await asyncio.wait_for(coro, timeout)
                    else:
                        await coro
                except TimeoutError:
                    logger.warning("Event handler timed out after %s seconds", timeout)
                except Exception:
                    logger.exception("Event handler failed")

        await asyncio.gather(*(run(handler) for handler in handlers))
