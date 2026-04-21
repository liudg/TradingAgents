from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from .indicators import latest_close, percent_change
from .schemas import (
    MarketMonitorEvidenceRef,
    MarketMonitorFactSheet,
    MarketMonitorSourceCoverage,
)


def _frame_to_market_fact(symbol: str, frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "symbol": symbol,
            "available": False,
            "rows": 0,
        }
    return {
        "symbol": symbol,
        "available": True,
        "rows": int(len(frame.index)),
        "latest_close": latest_close(frame),
        "change_5d_pct": round(percent_change(frame["Close"], 5), 2) if "Close" in frame else 0.0,
        "change_20d_pct": round(percent_change(frame["Close"], 20), 2) if "Close" in frame else 0.0,
        "last_trade_date": frame.index.max().date().isoformat() if isinstance(frame.index, pd.Index) and len(frame.index) else None,
    }


def build_market_fact_sheet(
    *,
    as_of_date: date,
    generated_at: datetime | None,
    core_data: dict[str, pd.DataFrame],
    local_market_data: dict[str, Any],
    derived_metrics: dict[str, Any],
    source_coverage: MarketMonitorSourceCoverage,
    open_gaps: list[str],
    notes: list[str],
    search_facts: list[dict[str, Any]] | None = None,
) -> MarketMonitorFactSheet:
    timestamp = generated_at or datetime.now(timezone.utc)
    symbol_facts = {
        symbol: _frame_to_market_fact(symbol, frame)
        for symbol, frame in core_data.items()
    }
    local_facts = {
        "symbols": symbol_facts,
        "market_proxies": local_market_data,
    }
    evidence_refs: list[MarketMonitorEvidenceRef] = []
    for symbol, fact in symbol_facts.items():
        if not fact.get("available"):
            continue
        snippet = f"{symbol} close={fact.get('latest_close')} 5d={fact.get('change_5d_pct')}% 20d={fact.get('change_20d_pct')}%"
        evidence_refs.append(
            MarketMonitorEvidenceRef(
                source_type="local_market_data",
                source_label=f"{symbol} 日线",
                snippet=snippet,
                timestamp=timestamp,
                confidence="high",
                metadata={
                    "symbol": symbol,
                    "rows": fact.get("rows"),
                    "last_trade_date": fact.get("last_trade_date"),
                },
            )
        )
    return MarketMonitorFactSheet(
        as_of_date=as_of_date,
        generated_at=timestamp,
        local_facts=local_facts,
        derived_metrics=derived_metrics,
        search_facts=search_facts or [],
        open_gaps=open_gaps,
        source_coverage=source_coverage,
        evidence_refs=evidence_refs,
        notes=notes,
    )
