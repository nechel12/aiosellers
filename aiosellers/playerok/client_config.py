"""Client configuration for Playerok."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.state import StateStore


@dataclass
class PlayerokClientConfig:
    """Configuration for Playerok client.

    Attributes:
        access_token: PlayerOK access token (or set PLAYEROK_ACCESS_TOKEN env var)
        user_agent: Custom user agent string
        request_timeout: Request timeout in seconds
        base_url: Base URL for PlayerOK API
        ws_url: Optional WebSocket URL (defaults to the matching PlayerOK feed)
        use_identity_map: Enable identity map for maintaining object identity
        identity_map_limit: Maximum cached entities per identity bucket (None = unlimited)
        include_own: Emit the seller's own messages as events (default: skip them)
        handler_timeout: Max seconds a single event handler may run (None disables)
        max_concurrent_handlers: How many handlers of one event run in parallel
        state: Optional store for cursors and dedup windows that survive restarts
        proxy: Proxy URL used for HTTP, downloads and WebSocket connections
    """

    access_token: str | None = field(default=None, repr=False)
    user_agent: str | None = None
    request_timeout: float = 10.0
    base_url: str = "https://playerok.com/"
    ws_url: str | None = None
    use_identity_map: bool = True
    identity_map_limit: int | None = 5000
    include_own: bool = False
    handler_timeout: float | None = 30.0
    max_concurrent_handlers: int = 10
    state: StateStore | None = None
    proxy: str | None = field(default=None, repr=False)
