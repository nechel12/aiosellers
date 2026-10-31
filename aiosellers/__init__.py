"""All-in-one sellers API: FunPay, Playerok and GGsel behind one package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("aiosellers-nechel12")
except PackageNotFoundError:  # pragma: no cover - source tree without installed metadata
    __version__ = "0.3.0"

from .core import (
    CAPABILITIES,
    Capability,
    EventKind,
    HubEvent,
    MediaPathNotAllowedError,
    MemoryStateStore,
    Platform,
    SellerClient,
    SellerHub,
    Session,
    SQLiteStateStore,
    StateStore,
    capabilities_for,
    event_kind,
)
from .funpay import FunPay, FunPayClientConfig
from .ggsel import GGsel, GGselClientConfig
from .playerok import Playerok, PlayerokClientConfig

__all__ = [
    "CAPABILITIES",
    "Capability",
    "EventKind",
    "FunPay",
    "FunPayClientConfig",
    "GGsel",
    "GGselClientConfig",
    "HubEvent",
    "MediaPathNotAllowedError",
    "MemoryStateStore",
    "Platform",
    "Playerok",
    "PlayerokClientConfig",
    "SQLiteStateStore",
    "SellerClient",
    "SellerHub",
    "Session",
    "StateStore",
    "capabilities_for",
    "event_kind",
    "__version__",
]
