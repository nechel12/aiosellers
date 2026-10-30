import asyncio
import os
import random
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

from ..core.config import PlayerokConfig
from ..core.constants import CLOUDFLARE_SIGNATURES
from ..core.exceptions import CloudflareDetected, RateLimitedError, RequestFailedError

DOWNLOAD_HOSTS_ENV = "PLAYEROK_DOWNLOAD_HOSTS"
REQUEST_ATTEMPTS = 3
DOWNLOAD_ATTEMPTS = 3


def _retry_after(headers: Any) -> float | None:
    if headers is None:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return None


def _backoff(attempt: int, retry_after: float | None = None) -> float:
    if retry_after is not None:
        return retry_after
    return min(8.0, 0.5 * (2**attempt)) + random.uniform(0, 0.1)


class PlayerokTransport:
    """
    Shared network transport for a single Playerok session.

    Owns one underlying TLS/HTTP client (tls_requests.AsyncClient) that is reused by all raw services.
    """

    def __init__(self, access_token: str | None = None, config: PlayerokConfig | None = None):
        # Lazy import so `aiosellers.playerok` can be imported without optional deps installed
        # (useful for tooling/tests in environments without network access).
        from tls_requests import AsyncClient  # type: ignore

        self._access_token = access_token or os.getenv("PLAYEROK_ACCESS_TOKEN")
        self._config = config or PlayerokConfig()

        if not self._access_token:
            raise RuntimeError(
                "Please provide playerok access token or fill PLAYEROK_ACCESS_TOKEN environment variable."
            )

        self._client = AsyncClient(
            cookies={"token": self._access_token},
            headers=self._config.headers,
            timeout=self._config.request_timeout,
        )
        self._download_client: Any | None = None
        self._download_hosts = self._build_download_hosts(self._config.base_url)

    @property
    def config(self) -> PlayerokConfig:
        return self._config

    @staticmethod
    def _build_download_hosts(base_url: str) -> set[str]:
        hosts = {"playerok.com"}
        host = (urlparse(base_url).hostname or "").lower()
        if host:
            hosts.add(host)
            parts = host.split(".")
            if len(parts) >= 2:
                hosts.add(".".join(parts[-2:]))
        extra = os.getenv(DOWNLOAD_HOSTS_ENV, "")
        hosts.update(part.strip().lower() for part in extra.split(",") if part.strip())
        return hosts

    def _check_download_url(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            url = urljoin(self._config.base_url, url)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported URL scheme for download: {parsed.scheme}")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("Download URLs must not contain credentials")
        host = (parsed.hostname or "").lower()
        if not host or not any(
            host == allowed or host.endswith("." + allowed) for allowed in self._download_hosts
        ):
            raise PermissionError(
                f"Refusing to download from untrusted host {host!r}; "
                f"allowed hosts: {', '.join(sorted(self._download_hosts))}"
            )
        return url

    def _get_download_client(self) -> Any:
        # Downloads must not carry the access token cookie, so they use a separate
        # unauthenticated client instead of the session client.
        if self._download_client is None:
            from tls_requests import AsyncClient  # type: ignore

            self._download_client = AsyncClient(
                headers={"user-agent": self._config.user_agent},
                timeout=self._config.request_timeout,
            )
        return self._download_client

    @staticmethod
    def _raise_if_cloudflare(response: Any) -> None:
        # tls_requests.Response has .text property
        if any(sig in response.text for sig in CLOUDFLARE_SIGNATURES):
            raise CloudflareDetected("The cloudflare protection is detected.")

    async def _exchange(
        self,
        method: Literal["get", "post"],
        url: str,
        payload: dict[str, Any],
        request_headers: dict[str, str],
        files: dict[str, Any] | None,
    ) -> Any:
        if method == "get":
            return await self._client.get(url=url, headers=request_headers, params=payload)
        if files:
            # Let the client set proper multipart boundary.
            request_headers.pop("content-type", None)
            return await self._client.post(
                url=url, headers=request_headers, data=payload, files=files
            )
        return await self._client.post(url=url, headers=request_headers, json=payload)

    async def request(
        self,
        method: Literal["get", "post"],
        url: str,
        payload: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
    ) -> Any:
        if method not in ("get", "post"):
            raise RuntimeError(f"Unsupported HTTP method: {method}")

        request_headers = self._config.headers.copy()
        if headers is not None:
            request_headers.update(headers)

        if not url.startswith("http"):
            url = self._config.base_url + url

        payload = payload or {}
        # POST is not idempotent, so only GET is retried automatically.
        attempts = REQUEST_ATTEMPTS if method == "get" else 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                response = await self._exchange(method, url, payload, request_headers, files)
            except Exception as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                await asyncio.sleep(_backoff(attempt))
                continue

            self._raise_if_cloudflare(response)

            status = getattr(response, "status_code", 200)
            if status < 400:
                return response

            retry_after = _retry_after(getattr(response, "headers", None))
            if status == 429:
                last_error = RateLimitedError(f"Playerok rate limited the request: HTTP 429 ({url})")
                if attempt + 1 >= attempts:
                    raise last_error
                await asyncio.sleep(_backoff(attempt, retry_after))
                continue

            if status >= 500 and attempt + 1 < attempts:
                last_error = RequestFailedError(f"Playerok request failed: HTTP {status} ({url})")
                await asyncio.sleep(_backoff(attempt, retry_after))
                continue

            raise RequestFailedError(f"Playerok request failed: HTTP {status} ({url})")

        raise RequestFailedError(f"Playerok request failed: {url}: {last_error}") from last_error

    async def download(self, url: str) -> bytes:
        """Download a file by URL from an allowlisted host without the session cookie."""
        url = self._check_download_url(url)
        client = self._get_download_client()
        last_error: Exception | None = None

        for attempt in range(DOWNLOAD_ATTEMPTS):
            retry_after = None
            try:
                response = await client.get(url)
            except Exception as exc:
                last_error = exc
            else:
                status = getattr(response, "status_code", 200)
                if 200 <= status < 300:
                    content = getattr(response, "content", None)
                    if content is not None:
                        return content
                    return getattr(response, "text", "").encode()

                retry_after = _retry_after(getattr(response, "headers", None))
                if status == 429:
                    last_error = RateLimitedError(
                        f"Playerok rate limited the download: HTTP 429 ({url})"
                    )
                elif status >= 500:
                    last_error = RequestFailedError(
                        f"Playerok download failed: HTTP {status} ({url})"
                    )
                else:
                    raise RequestFailedError(f"Playerok download failed: HTTP {status} ({url})")

            if attempt + 1 < DOWNLOAD_ATTEMPTS:
                await asyncio.sleep(_backoff(attempt, retry_after))

        if isinstance(last_error, RateLimitedError):
            raise last_error
        raise RequestFailedError(f"Failed to download {url}: {last_error}") from last_error

    async def close(self) -> None:
        if self._download_client is not None:
            await self._download_client.aclose()
            self._download_client = None
        await self._client.aclose()
