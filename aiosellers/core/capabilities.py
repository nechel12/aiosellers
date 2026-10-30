"""Platform identifiers and the capability matrix."""

from __future__ import annotations

from enum import Flag, StrEnum, auto


class Platform(StrEnum):
    FUNPAY = "funpay"
    PLAYEROK = "playerok"
    GGSEL = "ggsel"


class Capability(Flag):
    NONE = 0
    MESSAGES = auto()
    ORDERS = auto()
    PURCHASES = auto()
    DEALS = auto()
    REVIEWS = auto()
    LIST_MANAGEMENT = auto()
    IMAGE_UPLOAD = auto()
    ITEM_PRIORITY = auto()
    WEBSOCKET = auto()


CAPABILITIES: dict[Platform, Capability] = {
    Platform.FUNPAY: (
        Capability.MESSAGES
        | Capability.ORDERS
        | Capability.PURCHASES
        | Capability.REVIEWS
        | Capability.LIST_MANAGEMENT
        | Capability.IMAGE_UPLOAD
    ),
    Platform.PLAYEROK: (
        Capability.MESSAGES
        | Capability.DEALS
        | Capability.REVIEWS
        | Capability.LIST_MANAGEMENT
        | Capability.IMAGE_UPLOAD
        | Capability.ITEM_PRIORITY
        | Capability.WEBSOCKET
    ),
    Platform.GGSEL: (
        Capability.MESSAGES
        | Capability.ORDERS
        | Capability.REVIEWS
        | Capability.LIST_MANAGEMENT
    ),
}


def capabilities_for(platform: Platform | str) -> Capability:
    """Return what a platform can do, so shared code can branch without hardcoding."""
    return CAPABILITIES[Platform(platform)]
