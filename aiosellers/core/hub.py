"""Multi-platform facade: one lifecycle and one event stream for several sessions."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from .capabilities import Capability, Platform, capabilities_for
from .events import EventKind, HubEvent, event_kind

logger = logging.getLogger("aiosellers.hub")


@runtime_checkable
class SellerClient(Protocol):
    """What the hub needs from a platform client; FunPay, Playerok and GGsel match."""

    async def start(self) -> None: ...

    async def close(self) -> None: ...

    def listen(self, **options: Any) -> AsyncIterator[Any]: ...


@dataclass(slots=True, eq=False)
class Session:
    id: str
    platform: Platform
    client: SellerClient
    listen_options: dict[str, Any] = field(default_factory=dict)

    @property
    def capabilities(self) -> Capability:
        return capabilities_for(self.platform)


class SellerHub:
    """Runs several platform sessions together and merges their events.

    The hub owns start/close ordering and tags every event with its platform and
    session id. It does not normalize platform payloads: ``HubEvent.event`` is the
    original event object, and ``HubEvent.kind`` is the portable category.
    """

    def __init__(self, *, stream_buffer: int = 1000) -> None:
        self._sessions: dict[str, Session] = {}
        self._counters: dict[Platform, int] = {}
        self._stream_buffer = max(1, stream_buffer)

    def __len__(self) -> int:
        return len(self._sessions)

    @property
    def sessions(self) -> tuple[Session, ...]:
        return tuple(self._sessions.values())

    def add(
        self,
        client: SellerClient,
        *,
        platform: Platform | str,
        session_id: str | None = None,
        listen_options: dict[str, Any] | None = None,
    ) -> Session:
        platform = Platform(platform)
        if session_id is None:
            counter = self._counters.get(platform, 0) + 1
            self._counters[platform] = counter
            session_id = f"{platform.value}-{counter}"
        if session_id in self._sessions:
            raise ValueError(f"Session {session_id!r} is already registered")
        session = Session(
            id=session_id,
            platform=platform,
            client=client,
            listen_options=dict(listen_options or {}),
        )
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> Session:
        try:
            return self._sessions[session_id]
        except KeyError:
            raise KeyError(f"Unknown session {session_id!r}") from None

    async def start(self) -> None:
        """Start every session; if one fails, close the ones already started."""
        started: list[Session] = []
        try:
            for session in self._sessions.values():
                await session.client.start()
                started.append(session)
        except BaseException:
            await asyncio.gather(
                *(session.client.close() for session in started), return_exceptions=True
            )
            raise

    async def close(self) -> None:
        """Close every session; failures are logged and do not block the rest."""
        results = await asyncio.gather(
            *(session.client.close() for session in self._sessions.values()),
            return_exceptions=True,
        )
        for session, result in zip(self._sessions.values(), results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Failed to close %s session %s", session.platform.value, session.id,
                    exc_info=result,
                )

    async def __aenter__(self) -> SellerHub:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        await self.close()

    async def stream(self) -> AsyncIterator[HubEvent]:
        """Merge listeners of all sessions until every listener stops.

        Sessions must be started first; the hub does not start them implicitly.
        Breaking out of the loop cancels all listener tasks.
        """
        if not self._sessions:
            raise RuntimeError("The hub has no sessions")

        queue: asyncio.Queue[HubEvent | tuple[str, None]] = asyncio.Queue(
            maxsize=self._stream_buffer
        )

        async def pump(session: Session) -> None:
            try:
                async for event in session.client.listen(**session.listen_options):
                    await queue.put(
                        HubEvent(
                            platform=session.platform,
                            session_id=session.id,
                            kind=event_kind(session.platform, event),
                            event=event,
                        )
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Listener of %s session %s stopped", session.platform.value, session.id
                )
            finally:
                await queue.put((session.id, None))

        tasks = [asyncio.create_task(pump(session)) for session in self._sessions.values()]
        pending = len(tasks)
        try:
            while pending:
                item = await queue.get()
                if isinstance(item, tuple):
                    pending -= 1
                    continue
                yield item
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


__all__ = ["EventKind", "SellerClient", "SellerHub", "Session"]
