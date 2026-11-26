"""Portable error categories shared by the seller adapters."""

from __future__ import annotations

from typing import Any


class AiosellersError(Exception):
    """Base class for errors classified by the library."""


class AuthError(AiosellersError):
    """The platform rejected the session or credentials."""


class ConfigurationError(AiosellersError, RuntimeError):
    """A required client setting is missing or invalid."""


class TransientError(AiosellersError):
    """A temporary upstream failure; this does not make a write safe to repeat."""


class RateLimitedError(TransientError):
    """A rate limit, optionally with the server's suggested delay in seconds."""

    def __init__(
        self, message: str = "", *, retry_after: float | None = None, **kwargs: Any
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, **kwargs)
