"""Client configuration for FunPay."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..core.state import StateStore


@dataclass
class FunPayClientConfig:
    """Configuration for the FunPay client.

    Attributes:
        golden_key: FunPay golden_key cookie (or set FUNPAY_GOLDEN_KEY).
        user_agent: Desktop user agent. None selects the built-in Chrome UA.
        request_timeout: Request timeout in seconds.
        base_url: FunPay origin, with or without a trailing slash.
        locale: Optional locale prefix. ru and None stay unprefixed.
        proxy: Proxy URL passed through to tls_requests when supported.
        use_identity_map: Reuse entity instances for the same id.
        poll_interval: Seconds between listener ticks.
        session_refresh_seconds: How long a parsed home page stays fresh.
        handler_timeout: Max seconds a single event handler may run (None disables).
        max_concurrent_handlers: How many handlers of one event run in parallel.
        max_concurrent_requests: How many HTTP requests one session may run at once.
        state: Optional store for cursors and dedup windows that survive restarts.
        bot_mark: Add the invisible BOT_MARK to outgoing messages and reviews.
    """

    golden_key: str | None = None
    user_agent: str | None = None
    request_timeout: float = 10.0
    base_url: str = "https://funpay.com/"
    locale: Literal["ru", "en", "uk"] | None = None
    proxy: str | None = None
    use_identity_map: bool = True
    poll_interval: float = 6.0
    session_refresh_seconds: float = 2400.0
    handler_timeout: float | None = 30.0
    max_concurrent_handlers: int = 10
    max_concurrent_requests: int = 4
    state: StateStore | None = None
    bot_mark: bool = True
