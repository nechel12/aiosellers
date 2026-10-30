"""Client configuration for GGsel."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.state import StateStore


@dataclass
class GGselClientConfig:
    """Configuration for the GGsel seller client.

    Attributes:
        api_key: Seller API key (or set the GGSEL_API_KEY env var)
        seller_id: GGsel seller id (or set the GGSEL_SELLER_ID env var)
        user_agent: Custom user agent string
        request_timeout: Request timeout in seconds
        base_url: Base URL of the seller API
        locale: Locale sent to product and review endpoints
        use_identity_map: Reuse the same entity object for the same id
        handler_timeout: Max seconds a single event handler may run (None disables)
        max_concurrent_handlers: How many handlers of one event run in parallel
        poll_interval: Seconds between polling ticks
        state: Optional store for chat cursors and dedup windows across restarts
    """

    api_key: str | None = None
    seller_id: int | None = None
    user_agent: str | None = None
    request_timeout: float = 10.0
    base_url: str = "https://seller.ggsel.com/"
    locale: str = "ru-RU"
    use_identity_map: bool = True
    handler_timeout: float | None = 30.0
    max_concurrent_handlers: int = 10
    poll_interval: float = 5.0
    state: StateStore | None = None
