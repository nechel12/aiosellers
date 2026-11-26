"""Multi-platform facade: one lifecycle and one event stream for several sessions."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

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

    @property
    def account_id(self) -> str | None:
        field = {
            Platform.FUNPAY: "account_id",
            Platform.PLAYEROK: "me_id",
            Platform.GGSEL: "seller_id",
        }
        value = getattr(self.client, field[self.platform], None)
        return str(value) if isinstance(value, (int, str)) and value else None


@dataclass(slots=True)
class _End:
    session: Session
    error: Exception | None


@dataclass(slots=True)
class _Delivery:
    event: HubEvent
    resume: asyncio.Future[None] | None


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
        declared = getattr(client, "platform", None)
        if declared is not None and Platform(declared) is not platform:
            raise ValueError(
                f"Client platform {Platform(declared).value!r} does not match {platform.value!r}"
            )
        if session_id is None:
            counter = self._counters.get(platform, 0)
            while True:
                counter += 1
                candidate = f"{platform.value}-{counter}"
                if candidate not in self._sessions:
                    session_id = candidate
                    break
            self._counters[platform] = counter
        elif session_id.startswith(f"{platform.value}-"):
            suffix = session_id[len(platform.value) + 1 :]
            if suffix.isdigit():
                self._counters[platform] = max(self._counters.get(platform, 0), int(suffix))
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
        """Start every session; if one fails, close it and the ones already started."""
        started: list[Session] = []
        try:
            for session in self._sessions.values():
                started.append(session)
                await session.client.start()
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
                    "Failed to close %s session %s",
                    session.platform.value,
                    session.id,
                    exc_info=result,
                )

    async def __aenter__(self) -> SellerHub:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        await self.close()

    async def stream(
        self, *, error_policy: Literal["log", "yield", "raise"] = "log", buffered: bool = True
    ) -> AsyncGenerator[HubEvent, None]:
        """Merge listeners of all sessions until every listener stops.

        Sessions must be started first; the hub does not start them implicitly.
        Use ``aclosing()`` for early exit. ``error_policy="yield"`` reports a failed session
        while others continue; ``"raise"`` re-raises its exception and stops all pumps.
        With ``buffered=False``, a producer is resumed only when the consumer requests
        another event. Persist the received event before doing that if replay matters.
        """
        if not self._sessions:
            raise RuntimeError("The hub has no sessions")
        if error_policy not in {"log", "yield", "raise"}:
            raise ValueError("Unknown stream error policy")

        queue: asyncio.Queue[_Delivery | _End] = asyncio.Queue(maxsize=self._stream_buffer)
        closing = False

        async def pump(session: Session) -> None:
            error: Exception | None = None
            try:
                listener = session.client.listen(**session.listen_options)
                try:
                    async for event in listener:
                        resume = None if buffered else asyncio.get_running_loop().create_future()
                        await queue.put(
                            _Delivery(
                                HubEvent(
                                    platform=session.platform,
                                    session_id=session.id,
                                    kind=event_kind(session.platform, event),
                                    event=event,
                                    account_id=session.account_id,
                                ),
                                resume,
                            )
                        )
                        if resume is not None:
                            await resume
                finally:
                    close = getattr(listener, "aclose", None)
                    if close is not None:
                        await close()
            except asyncio.CancelledError:
                if closing:
                    raise
                error = RuntimeError("The session listener was cancelled")
                if error_policy == "log":
                    logger.warning(
                        "Listener of %s session %s was cancelled",
                        session.platform.value,
                        session.id,
                    )
            except Exception as exc:
                error = exc
                if error_policy == "log":
                    logger.exception(
                        "Listener of %s session %s stopped", session.platform.value, session.id
                    )
            if closing:
                return
            await queue.put(_End(session, error))

        tasks = [asyncio.create_task(pump(session)) for session in self._sessions.values()]
        pending = len(tasks)
        try:
            while pending:
                item = await queue.get()
                if isinstance(item, _End):
                    pending -= 1
                    if item.error is not None:
                        if error_policy == "raise":
                            raise item.error
                        if error_policy == "yield":
                            yield HubEvent(
                                item.session.platform,
                                item.session.id,
                                EventKind.ERROR,
                                item.error,
                                item.session.account_id,
                            )
                    continue
                yield item.event
                if item.resume is not None and not item.resume.done():
                    item.resume.set_result(None)
        finally:
            closing = True
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


__all__ = ["EventKind", "SellerClient", "SellerHub", "Session"]
