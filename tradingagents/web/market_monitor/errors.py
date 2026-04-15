from __future__ import annotations


class MarketMonitorError(RuntimeError):
    """Base exception for market monitor failures."""


class MarketMonitorNotFoundError(MarketMonitorError):
    """Raised when a market monitor resource cannot be found."""

