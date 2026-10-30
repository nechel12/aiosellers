from __future__ import annotations

import os

DEFAULT_BASE_URL = "https://seller.ggsel.com/"
DEFAULT_USER_AGENT = "aiosellers-ggsel/1.0"


class GGselConfig:
    def __init__(
        self,
        *,
        user_agent: str | None = None,
        request_timeout: float | None = None,
        base_url: str | None = None,
        locale: str = "ru-RU",
    ):
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.request_timeout = request_timeout or 10.0
        self.base_url: str = (
            base_url or os.getenv("GGSEL_BASE_URL", DEFAULT_BASE_URL) or DEFAULT_BASE_URL
        )
        self.locale = locale

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
            "lang": self.lang_header,
            "locale": self.locale_header,
        }

    @property
    def locale_header(self) -> str:
        return self.locale

    @property
    def lang_header(self) -> str:
        return self.locale.split("-")[0].lower()
