from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class Balance:
    """GGsel wallet: free funds, blocked funds and restricted top-ups."""

    free: float | None = None
    locked: float | None = None
    plus: float | None = None
