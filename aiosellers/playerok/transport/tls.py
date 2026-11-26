import asyncio
import json
import os
import random
from math import isfinite
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

import httpx

from ...core.exceptions import ConfigurationError
from ...core.retry import retry_after_seconds
from ..core.config import PlayerokConfig
from ..core.constants import CLOUDFLARE_SIGNATURES
from ..core.exceptions import (
    CloudflareDetected,
    DownloadTooLargeError,
    GraphQLError,
    RateLimitedError,
    RequestFailedError,
    TransientRequestError,
    Unauthorized,
)
from ..core.utils import has_auth_error

DOWNLOAD_HOSTS_ENV = "PLAYEROK_DOWNLOAD_HOSTS"
REQUEST_ATTEMPTS = 3
DOWNLOAD_ATTEMPTS = 3
DOWNLOAD_REDIRECT_LIMIT = 3
DEFAULT_DOWNLOAD_MAX_BYTES = 16 * 1024 * 1024


def _retry_after(headers: Any) -> float | None:
    if headers is None:
        return None
    value = headers.get("retry-after") or headers.get("Retry-After")
    return retry_after_seconds(str(value) if value is not None else None)


def _backoff(attempt: int, retry_after: float | None = None) -> float:
    if retry_after is not None:
        return retry_after
    return min(8.0, 0.5 * (2**attempt)) + random.uniform(0, 0.1)


def _response_body(response: Any) -> str:
    """Return a short printable body snippet for error messages."""
    text = getattr(response, "text", "") or ""
    return str(text).strip()


def _body_suffix(response: Any) -> str:
    body = _response_body(response)
    return f" body={body[:200]!r}" if body else ""


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
            raise ConfigurationError(
                "Please provide playerok access token or fill PLAYEROK_ACCESS_TOKEN environment variable."
            )

        client_kwargs: dict[str, Any] = {
            "cookies": {"token": self._access_token},
            "headers": self._config.headers,
            "timeout": self._config.request_timeout,
        }
        if self._config.proxy:
            client_kwargs["proxy"] = self._config.proxy
        self._client = AsyncClient(**client_kwargs)
        self._download_client: httpx.AsyncClient | None = None
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

    def _get_download_client(self) -> httpx.AsyncClient:
        # Downloads must not carry the access token cookie, so they use a separate
        # unauthenticated client instead of the session client.
        if self._download_client is None:
            self._download_client = httpx.AsyncClient(
                headers={"User-Agent": self._config.user_agent, "Accept-Encoding": "identity"},
                timeout=self._config.request_timeout,
                proxy=self._config.proxy or None,
                trust_env=False,
                follow_redirects=False,
            )
        return self._download_client

    @staticmethod
    def _raise_if_cloudflare(response: Any) -> None:
        # Cloudflare challenge pages are HTML error pages.  Looking at every
        # GraphQL response caused false positives when a chat message merely
        # contained one of the signature strings.
        status = getattr(response, "status_code", 200)
        text = getattr(response, "text", "") or ""
        headers = getattr(response, "headers", None)
        content_type = ""
        if headers is not None and hasattr(headers, "get"):
            content_type = str(headers.get("content-type") or "").lower()
            if (
                str(headers.get("cf-mitigated") or headers.get("Cf-Mitigated")).lower()
                == "challenge"
            ):
                raise CloudflareDetected("PlayerOK returned a Cloudflare challenge")
        is_html = content_type.startswith("text/html") or text.lstrip().startswith("<")
        if (status >= 400 or is_html) and any(sig in text for sig in CLOUDFLARE_SIGNATURES):
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
        # GraphQL multipart requests use `operations`/`map` even when there are
        # no files; tls_requests must receive them as form data, not JSON.
        if files or ("operations" in payload and "map" in payload):
            # Let the client set proper multipart boundary.
            request_headers.pop("content-type", None)
            return await self._client.post(
                url=url, headers=request_headers, data=payload, files=files or {}
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
        retry: bool | None = None,
    ) -> Any:
        if method not in ("get", "post"):
            raise RuntimeError(f"Unsupported HTTP method: {method}")

        request_headers = self._config.headers.copy()
        if headers is not None:
            request_headers.update(headers)

        if not url.startswith("http"):
            url = self._config.base_url.rstrip("/") + "/" + url.lstrip("/")

        payload = payload or {}
        # POST remains single-shot unless a read-only operation explicitly opts in.
        should_retry = method == "get" if retry is None else retry
        attempts = REQUEST_ATTEMPTS if should_retry else 1
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
            if status == 401:
                raise Unauthorized("PlayerOK rejected the session (HTTP 401)")
            if status == 403:
                try:
                    data = json.loads(_response_body(response))
                except ValueError:
                    data = None
                if has_auth_error(data):
                    raise Unauthorized("PlayerOK rejected the session (HTTP 403)")
            if status < 400:
                body = _response_body(response)
                if body and not body.lstrip().startswith(("{", "[")):
                    raise GraphQLError(
                        f"Playerok returned non-JSON response: HTTP {status} ({url}) "
                        f"body={body[:200]!r}"
                    )
                return response

            retry_after = _retry_after(getattr(response, "headers", None))
            suffix = _body_suffix(response)
            if status == 429:
                last_error = RateLimitedError(
                    f"Playerok rate limited the request: HTTP 429 ({url}){suffix}",
                    retry_after=retry_after,
                )
                if attempt + 1 >= attempts:
                    raise last_error
                await asyncio.sleep(_backoff(attempt, retry_after))
                continue

            if status >= 500 and attempt + 1 < attempts:
                last_error = RequestFailedError(
                    f"Playerok request failed: HTTP {status} ({url}){suffix}"
                )
                await asyncio.sleep(_backoff(attempt, retry_after))
                continue

            error = TransientRequestError if status in {500, 502, 503, 504} else RequestFailedError
            raise error(f"Playerok request failed: HTTP {status} ({url}){suffix}")

        error = (
            TransientRequestError
            if isinstance(last_error, (ConnectionError, TimeoutError))
            else RequestFailedError
        )
        raise error(f"Playerok request failed: {url}: {last_error}") from last_error

    async def _download_once(
        self, client: httpx.AsyncClient, url: str, max_bytes: int
    ) -> tuple[int, float | None, bytes | None]:
        current_url = url
        for redirect_count in range(DOWNLOAD_REDIRECT_LIMIT + 1):
            async with client.stream("GET", current_url) as response:
                status = response.status_code
                if status in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise RequestFailedError(
                            "PlayerOK download redirect has no Location header"
                        )
                    if redirect_count >= DOWNLOAD_REDIRECT_LIMIT:
                        raise RequestFailedError(
                            f"PlayerOK download exceeded {DOWNLOAD_REDIRECT_LIMIT} redirects"
                        )
                    current_url = self._check_download_url(urljoin(current_url, location))
                    continue
                if not 200 <= status < 300:
                    return status, _retry_after(response.headers), None
                return status, None, await self._read_download(response, max_bytes)

        raise AssertionError("unreachable")

    @staticmethod
    async def _read_download(response: httpx.Response, max_bytes: int) -> bytes:
        if response.headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
            raise RequestFailedError("PlayerOK download used an unexpected content encoding")
        length = response.headers.get("content-length")
        try:
            announced = int(length) if length is not None else None
        except ValueError:
            announced = None
        if announced is not None and announced > max_bytes:
            raise DownloadTooLargeError(f"PlayerOK download exceeds {max_bytes} bytes")
        data = bytearray()
        async for chunk in response.aiter_raw():
            if len(chunk) > max_bytes - len(data):
                raise DownloadTooLargeError(f"PlayerOK download exceeds {max_bytes} bytes")
            data.extend(chunk)
        return bytes(data)

    async def download(
        self, url: str, *, max_bytes: int = DEFAULT_DOWNLOAD_MAX_BYTES, timeout: float | None = None
    ) -> bytes:
        """Download a file by URL from an allowlisted host without the session cookie."""
        if type(max_bytes) is not int or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        if timeout is not None and (not isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be positive and finite")
        url = self._check_download_url(url)
        async with asyncio.timeout(timeout):
            return await self._download(url, max_bytes)

    async def _download(self, url: str, max_bytes: int) -> bytes:
        client = self._get_download_client()
        last_error: Exception | None = None

        for attempt in range(DOWNLOAD_ATTEMPTS):
            retry_after = None
            try:
                status, retry_after, content = await self._download_once(client, url, max_bytes)
            except httpx.TransportError as exc:
                last_error = exc
            else:
                if content is not None:
                    return content
                if status == 429:
                    last_error = RateLimitedError(
                        "PlayerOK rate limited the download: HTTP 429", retry_after=retry_after
                    )
                elif status >= 500:
                    error = (
                        TransientRequestError
                        if status in {500, 502, 503, 504}
                        else RequestFailedError
                    )
                    last_error = error(f"PlayerOK download failed: HTTP {status}")
                else:
                    raise RequestFailedError(f"PlayerOK download failed: HTTP {status}")

            if attempt + 1 < DOWNLOAD_ATTEMPTS:
                await asyncio.sleep(_backoff(attempt, retry_after))

        if isinstance(last_error, RequestFailedError):
            raise last_error
        error = (
            TransientRequestError
            if isinstance(last_error, (httpx.TimeoutException, httpx.NetworkError))
            else RequestFailedError
        )
        raise error("PlayerOK download failed") from last_error

    async def close(self) -> None:
        if self._download_client is not None:
            await self._download_client.aclose()
            self._download_client = None
        await self._client.aclose()
