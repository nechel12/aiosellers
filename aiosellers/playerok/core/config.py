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
        ws_use_system_proxy: bool = False,
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
        origin_scheme = parsed.scheme if parsed.scheme in {"http", "https"} else "https"
        ws_scheme = "ws" if origin_scheme == "http" else "wss"
        authority = f"[{host}]" if ":" in host else host
        port = parsed.port
        if port is not None:
            authority = f"{authority}:{port}"
        self.origin = f"{origin_scheme}://{authority}"

        official = host == "playerok.com" or host.endswith(".playerok.com")
        base_path = parsed.path.rstrip("/")
        self.ws_url = ws_url or (
            "wss://ws.playerok.com/graphql"
            if official and origin_scheme == "https" and port in (None, 443) and not base_path
            else f"{ws_scheme}://{authority}{base_path}/graphql"
        )
        self.proxy = proxy
        self.ws_use_system_proxy = ws_use_system_proxy

    @property
    def headers(self):
        return BASE_HEADERS | {
            "User-Agent": self.user_agent,
        }
