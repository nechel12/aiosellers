"""All-in-one sellers API: FunPay, Playerok and GGsel behind one package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("aiosellers-nechel12")
except PackageNotFoundError:  # pragma: no cover - source tree without installed metadata
    __version__ = "0.5.0"

from .core import (
    CAPABILITIES,
    AiosellersError,
    AuthError,
    Capability,
    ConfigurationError,
    EventKind,
    HubEvent,
    HubEventData,
    MediaPathNotAllowedError,
    MemoryStateStore,
    Platform,
    RateLimitedError,
    SellerClient,
    SellerHub,
    SellerSession,
    Session,
    SQLiteStateStore,
    StateStore,
    TransientError,
    capabilities_for,
    event_kind,
)
from .funpay import FunPay, FunPayClientConfig
from .ggsel import GGsel, GGselClientConfig
from .playerok import Playerok, PlayerokClientConfig

__all__ = [
    "CAPABILITIES",
    "AiosellersError",
    "AuthError",
    "Capability",
    "ConfigurationError",
    "EventKind",
    "FunPay",
    "FunPayClientConfig",
    "GGsel",
    "GGselClientConfig",
    "HubEvent",
    "HubEventData",
    "MediaPathNotAllowedError",
    "MemoryStateStore",
    "Platform",
    "Playerok",
    "PlayerokClientConfig",
    "RateLimitedError",
    "SQLiteStateStore",
    "SellerClient",
    "SellerHub",
    "SellerSession",
    "Session",
    "StateStore",
    "TransientError",
    "capabilities_for",
    "event_kind",
    "__version__",
]
