import os
import random
from urllib.parse import urlparse

from .constants import BASE_HEADERS, EXAMPLE_USER_AGENTS


class PlayerokConfig:
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        request_timeout: float | None = None,
        base_url: str | None = None,
        proxy: str | None = None,
        ws_url: str | None = None,
    ):
        self.user_agent = user_agent or random.choice(EXAMPLE_USER_AGENTS)
        self.request_timeout = request_timeout or 10.0
        self.base_url: str = (
            base_url
            or os.getenv("PLAYEROK_BASE_URL", "https://playerok.com/")
            or "https://playerok.com/"
        )
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "playerok.com").lower()
        self.ws_url = ws_url or (
            "wss://ws.playerok.com/graphql"
            if host.endswith("playerok.com")
            else f"wss://{host}/graphql"
        )
        origin_scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
        self.origin = f"{origin_scheme}://{host}"
        self.proxy = proxy

    @property
    def headers(self):
        return BASE_HEADERS | {
            "User-Agent": self.user_agent,
        }
