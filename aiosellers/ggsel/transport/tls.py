from __future__ import annotations

import asyncio
import hashlib
import os
import random
import time
from typing import Any, Literal

from ..core.config import GGselConfig
from ..core.exceptions import (
    ApiError,
    RateLimitedError,
    RequestFailedError,
    UnauthorizedError,
)
from ..schemas import LoginResponse

LOGIN_PATH = "/api_sellers/api/apilogin"
REQUEST_ATTEMPTS = 3
TOKEN_REFRESH_MARGIN = 60.0


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


class GGselTransport:
    """HTTP transport with the V1 ApiLogin token flow.

    The token is a query parameter on every seller API call. It is refreshed
    ahead of ``valid_thru`` and once more after a 401 response.
    """

    def __init__(
        self,
        api_key: str | None = None,
        seller_id: int | str | None = None,
        config: GGselConfig | None = None,
    ):
        from tls_requests import AsyncClient  # type: ignore

        key = api_key or os.getenv("GGSEL_API_KEY")
        if not key:
            raise RuntimeError(
                "Please provide a GGsel API key or set the GGSEL_API_KEY environment variable."
            )
        raw_seller_id = seller_id if seller_id is not None else os.getenv("GGSEL_SELLER_ID")
        try:
            parsed_seller_id = int(raw_seller_id) if raw_seller_id not in (None, "") else None
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"Invalid GGsel seller id: {raw_seller_id!r}") from exc
        if parsed_seller_id is None:
            raise RuntimeError(
                "Please provide a GGsel seller id or set the GGSEL_SELLER_ID environment variable."
            )

        self._api_key = key
        self._seller_id = parsed_seller_id
        self._config = config or GGselConfig()
        self._client = AsyncClient(
            headers=self._config.headers,
            timeout=self._config.request_timeout,
        )
        self._token: str | None = None
        self._token_valid_until = 0.0
        self._token_lock = asyncio.Lock()
        self._closed = False

    @property
    def config(self) -> GGselConfig:
        return self._config

    @property
    def seller_id(self) -> int:
        return self._seller_id

    async def login(self) -> str:
        async with self._token_lock:
            if self._token and time.monotonic() < self._token_valid_until:
                return self._token

            timestamp = str(int(time.time()))
            # GGsel mandates SHA-256 for ApiLogin signatures; no passwords are hashed here.
            sign = hashlib.sha256(  # codeql[py/weak-sensitive-data-hashing]
                (self._api_key + timestamp).encode()
            ).hexdigest()
            data = await self._request_with_retries(
                "post",
                LOGIN_PATH,
                params=None,
                json_body={
                    "seller_id": self._seller_id,
                    "timestamp": timestamp,
                    "sign": sign,
                },
                auth=False,
                retry=True,
            )
            payload = LoginResponse.model_validate(data if isinstance(data, dict) else {})
            if not payload.token:
                raise UnauthorizedError(payload.desc or "GGsel did not return an access token")

            self._token = payload.token
            if payload.seller_id:
                self._seller_id = payload.seller_id
            self._token_valid_until = self._token_expiry(payload)
            return self._token

    @staticmethod
    def _token_expiry(payload: LoginResponse) -> float:
        now = time.time()
        if payload.valid_thru is None:
            return time.monotonic() + 3600
        remaining = payload.valid_thru.timestamp() - now
        return time.monotonic() + max(0.0, remaining - TOKEN_REFRESH_MARGIN)

    async def _token_after_unauthorized(self, expected: str) -> str:
        async with self._token_lock:
            if self._token == expected:
                self._token = None
                self._token_valid_until = 0.0
            elif self._token and time.monotonic() < self._token_valid_until:
                return self._token
        return await self.login()

    async def request(
        self,
        method: Literal["get", "post"],
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        retry: bool | None = None,
    ) -> Any:
        if self._closed:
            raise RuntimeError("GGsel transport is closed")
        if method not in ("get", "post"):
            raise RuntimeError(f"Unsupported HTTP method: {method}")

        token = await self.login()
        try:
            return await self._request_with_retries(
                method,
                path,
                params=params,
                json_body=json_body,
                auth=True,
                retry=retry,
                token=token,
            )
        except UnauthorizedError:
            if method == "post" and retry is not True:
                raise
            token = await self._token_after_unauthorized(token)
            return await self._request_with_retries(
                method,
                path,
                params=params,
                json_body=json_body,
                auth=True,
                retry=retry,
                token=token,
            )

    async def _request_with_retries(
        self,
        method: Literal["get", "post"],
        path: str,
        *,
        params: dict[str, Any] | None,
        json_body: Any | None,
        auth: bool,
        retry: bool | None,
        token: str | None = None,
    ) -> Any:
        attempts = REQUEST_ATTEMPTS if (retry if retry is not None else method == "get") else 1
        url = (
            path
            if path.startswith("http")
            else self._config.base_url.rstrip("/") + "/" + path.lstrip("/")
        )
        last_error: Exception | None = None

        for attempt in range(attempts):
            query = dict(params or {})
            if auth:
                request_token = token or self._token
                if not request_token:
                    raise UnauthorizedError("GGsel access token is not available")
                query["token"] = request_token

            try:
                response = await self._exchange(method, url, query, json_body)
            except Exception as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                await asyncio.sleep(_backoff(attempt))
                continue

            status = getattr(response, "status_code", 200)
            if status < 400:
                return self._decode(response)

            retry_after = _retry_after(getattr(response, "headers", None))
            if status == 401:
                raise UnauthorizedError(f"GGsel rejected the access token: HTTP 401 ({path})")
            if status == 429:
                last_error = RateLimitedError(f"GGsel rate limited the request: HTTP 429 ({path})")
                if attempt + 1 >= attempts:
                    raise last_error
                await asyncio.sleep(_backoff(attempt, retry_after))
                continue
            if status >= 500 and attempt + 1 < attempts:
                last_error = RequestFailedError(f"GGsel request failed: HTTP {status} ({path})")
                await asyncio.sleep(_backoff(attempt, retry_after))
                continue
            raise RequestFailedError(f"GGsel request failed: HTTP {status} ({path})")

        raise RequestFailedError(f"GGsel request failed: {path}: {last_error}") from last_error

    async def _exchange(
        self,
        method: Literal["get", "post"],
        url: str,
        params: dict[str, Any],
        json_body: Any | None,
    ) -> Any:
        headers = self._config.headers.copy()
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if method == "get":
            return await self._client.get(url=url, headers=headers, params=params)
        return await self._client.post(url=url, headers=headers, params=params, json=json_body)

    @staticmethod
    def _decode(response: Any) -> Any:
        text = getattr(response, "text", "")
        if not text:
            return {}
        try:
            data = response.json()
        except Exception as exc:
            stripped = text.lstrip()
            if stripped.startswith(("{", "[")):
                raise RequestFailedError("GGsel returned malformed JSON") from exc
            return text
        if isinstance(data, dict):
            retval = data.get("retval")
            if isinstance(retval, int) and retval < 0:
                raise ApiError(
                    data.get("retdesc") or "GGsel returned an error",
                    retval=retval,
                )
        return data

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._client.aclose()
