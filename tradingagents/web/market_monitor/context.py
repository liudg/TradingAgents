from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .schemas import MarketDataSnapshot, MarketMissingDataItem


class MarketMonitorContextPayload(BaseModel):
    as_of_date: str
    market_data_snapshot: MarketDataSnapshot
    missing_data: list[MarketMissingDataItem] = Field(default_factory=list)
    instructions: dict[str, Any] = Field(default_factory=dict)

