from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

import pandas as pd

from .indicators import _column_series, latest_close, percent_change
from .schemas import MarketMonitorEventFact, MarketMonitorEvidenceRef, MarketMonitorFactSheet


def _frame_to_market_fact(symbol: str, frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "symbol": symbol,
            "available": False,
            "rows": 0,
        }
    close = _column_series(frame, "Close")
    return {
        "symbol": symbol,
        "available": True,
        "rows": int(len(frame.index)),
        "latest_close": latest_close(frame),
        "change_5d_pct": round(percent_change(close, 5), 2),
        "change_20d_pct": round(percent_change(close, 20), 2),
        "last_trade_date": frame.index.max().date().isoformat() if isinstance(frame.index, pd.Index) and len(frame.index) else None,
    }


def build_market_fact_sheet(
    *,
    as_of_date: date,
    generated_at: datetime | None,
    core_data: dict[str, pd.DataFrame],
    local_market_data: dict[str, Any],
    derived_metrics: dict[str, Any],
    open_gaps: list[str],
    notes: list[str],
    event_fact_sheet: list[MarketMonitorEventFact] | None = None,
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
    evidence: list[MarketMonitorEvidenceRef] = []
    for symbol, fact in symbol_facts.items():
        if not fact.get("available"):
            continue
        snippet = f"{symbol} close={fact.get('latest_close')} 5d={fact.get('change_5d_pct')}% 20d={fact.get('change_20d_pct')}%"
        evidence.append(
            MarketMonitorEvidenceRef(
                source_type="local_market_data",
                source_label=f"{symbol} 日线",
                snippet=snippet,
                timestamp=timestamp,
                confidence=0.95,
                metadata={
                    "symbol": symbol,
                    "rows": fact.get("rows"),
                    "last_trade_date": fact.get("last_trade_date"),
                },
            )
        )
    for event in event_fact_sheet or []:
        evidence.append(
            MarketMonitorEvidenceRef(
                source_type="event_fact_sheet",
                source_label=f"{event.source_name}: {event.event}",
                snippet=event.source_summary,
                timestamp=event.observed_at,
                confidence=event.confidence,
                metadata={
                    "event_id": event.event_id,
                    "scope": event.scope,
                    "severity": event.severity,
                    "source_url": event.source_url,
                    "expires_at": event.expires_at.isoformat(),
                },
            )
        )
    return MarketMonitorFactSheet(
        as_of_date=as_of_date,
        generated_at=timestamp,
        local_facts=local_facts,
        derived_metrics=derived_metrics,
        event_fact_sheet=event_fact_sheet or [],
        open_gaps=open_gaps,
        evidence=evidence,
        notes=notes,
    )
