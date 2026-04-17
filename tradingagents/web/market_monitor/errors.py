from __future__ import annotations


class MarketMonitorError(RuntimeError):
    """Base exception for market monitor failures."""


class MarketMonitorNotFoundError(MarketMonitorError):
    """Raised when a market monitor resource cannot be found."""


class MarketMonitorCorruptedStateError(MarketMonitorError):
    """Raised when a persisted market monitor resource exists but cannot be read."""

