from __future__ import annotations

import asyncio
import time

from ..core.constants import BOT_MARK
from ..exceptions import RateLimitedError
from ..transport.tls import FunPayTransport


class RawBase:
    _RATE_LIMIT_ATTEMPTS = 3

    def __init__(self, transport: FunPayTransport) -> None:
        self.transport = transport

    @property
    def bot_mark(self) -> str:
        """Invisible marker for outgoing messages; empty when disabled."""
        config = getattr(self.transport, "_config", None)
        return BOT_MARK if getattr(config, "bot_mark", True) else ""

    async def _retry(self, factory):
        attempt = 0
        while True:
            try:
                return await factory()
            except RateLimitedError:
                attempt += 1
                if attempt >= self._RATE_LIMIT_ATTEMPTS:
                    raise
                delay = self.transport.rate_limited_until - time.monotonic()
                await asyncio.sleep(max(1.0, min(60.0, delay)))

    async def _call(self, fn, *, retry: bool = True):
        async def run():
            await self.transport.refresh_profile()
            return await fn()

        if retry:
            return await self._retry(run)
        return await run()
