"""Stop an in-flight poll without cancelling the task consuming its generator."""

import asyncio
from collections.abc import Coroutine
from contextlib import suppress
from typing import Any


class PollControl:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._active: asyncio.Task[list[Any]] | None = None

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    async def poll(self, operation: Coroutine[Any, Any, list[Any]]) -> list[Any]:
        task = asyncio.create_task(operation)
        self._active = task
        try:
            return await task
        except asyncio.CancelledError:
            consumer = asyncio.current_task()
            if self.stopped and consumer is not None and not consumer.cancelling():
                return []
            raise
        finally:
            self._active = None

    async def wait(self, seconds: float) -> None:
        with suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), seconds)

    def stop(self) -> None:
        if self.stopped:
            return
        self._stop.set()
        if self._active is not None:
            self._active.cancel()

    async def aclose(self) -> None:
        self.stop()
        if self._active is not None:
            await asyncio.gather(self._active, return_exceptions=True)
