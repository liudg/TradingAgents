from __future__ import annotations

from typing import Any

import pandas as pd

from .indicators import atr_percent, percent_change, sma


def _frame_series(frame: pd.DataFrame, column: str) -> pd.Series:
    value = frame.get(column, pd.Series(dtype=float))
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return pd.Series(dtype=float)
        value = value.iloc[:, 0]
    return value.dropna()


def build_market_snapshot(core_data: dict[str, pd.DataFrame], breadth_symbols: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    local_market_data: dict[str, Any] = {}
    derived_metrics: dict[str, Any] = {}

    breadth_states = []
    for symbol in breadth_symbols:
        frame = core_data.get(symbol, pd.DataFrame())
        close = _frame_series(frame, "Close")
        if close.empty:
            continue
        ma200 = sma(close, 200)
        latest_close = float(close.iloc[-1])
        latest_ma200 = float(ma200.dropna().iloc[-1]) if not ma200.dropna().empty else None
        above_ma200 = bool(latest_ma200 is not None and latest_close > latest_ma200)
        breadth_states.append(1.0 if above_ma200 else 0.0)

        local_market_data[symbol] = {
            "close": latest_close,
            "change_5d_pct": round(percent_change(close, 5), 2),
            "change_20d_pct": round(percent_change(close, 20), 2),
            "above_ma200": above_ma200,
        }

    spy = _frame_series(core_data.get("SPY", pd.DataFrame()), "Close")
    qqq = _frame_series(core_data.get("QQQ", pd.DataFrame()), "Close")
    iwm = _frame_series(core_data.get("IWM", pd.DataFrame()), "Close")
    vix = _frame_series(core_data.get("^VIX", pd.DataFrame()), "Close")

    if not spy.empty:
        spy_ma200 = sma(spy, 200).dropna()
        if not spy_ma200.empty:
            derived_metrics["spy_distance_to_ma200_pct"] = round(
                float((spy.iloc[-1] - spy_ma200.iloc[-1]) / spy_ma200.iloc[-1] * 100.0),
                2,
            )
        derived_metrics["spy_range_position_3m_pct"] = round(
            _range_position(spy, 63),
            2,
        )
        derived_metrics["spy_atr_pct"] = round(atr_percent(core_data["SPY"]), 2)
    if not qqq.empty:
        derived_metrics["qqq_change_20d_pct"] = round(percent_change(qqq, 20), 2)
    if not iwm.empty:
        derived_metrics["iwm_change_20d_pct"] = round(percent_change(iwm, 20), 2)
    if not vix.empty:
        derived_metrics["vix_close"] = round(float(vix.iloc[-1]), 2)

    derived_metrics["breadth_above_200dma_pct"] = round(
        (sum(breadth_states) / len(breadth_states) * 100.0) if breadth_states else 0.0,
        2,
    )
    derived_metrics["available_symbol_count"] = len(local_market_data)
    return local_market_data, derived_metrics


def _range_position(series: pd.Series, window: int) -> float:
    clean = series.dropna()
    if len(clean) < 2:
        return 0.0
    windowed = clean.tail(window)
    low = float(windowed.min())
    high = float(windowed.max())
    if high == low:
        return 50.0
    return (float(windowed.iloc[-1]) - low) / (high - low) * 100.0
