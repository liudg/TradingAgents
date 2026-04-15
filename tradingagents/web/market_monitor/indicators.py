from __future__ import annotations

from math import isnan

import pandas as pd


def latest_close(frame: pd.DataFrame) -> float | None:
    if frame.empty or "Close" not in frame:
        return None
    value = frame["Close"].dropna()
    return None if value.empty else float(value.iloc[-1])


def rolling_percentile(series: pd.Series, value: float, window: int = 252) -> float:
    clean = series.dropna().tail(window)
    if clean.empty:
        return 50.0
    return float((clean <= value).mean() * 100.0)


def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def percent_change(series: pd.Series, periods: int) -> float:
    clean = series.dropna()
    if len(clean) <= periods:
        return 0.0
    start = clean.iloc[-periods - 1]
    end = clean.iloc[-1]
    if start == 0:
        return 0.0
    return float((end - start) / start * 100.0)


def atr_percent(frame: pd.DataFrame, window: int = 14) -> float:
    if frame.empty or not {"High", "Low", "Close"}.issubset(frame.columns):
        return 0.0
    data = frame[["High", "Low", "Close"]].dropna()
    if len(data) < window + 1:
        return 0.0
    prev_close = data["Close"].shift(1)
    true_range = pd.concat(
        [
            data["High"] - data["Low"],
            (data["High"] - prev_close).abs(),
            (data["Low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(window=window, min_periods=window).mean().iloc[-1]
    close = data["Close"].iloc[-1]
    if close == 0 or isnan(atr):
        return 0.0
    return float(atr / close * 100.0)


def zone_from_score(score: float, zones: list[tuple[float, str]]) -> str:
    for threshold, name in zones:
        if score < threshold:
            return name
    return zones[-1][1]


def slope_state(delta_1d: float, delta_5d: float) -> str:
    if delta_1d > 3 and delta_5d > 8:
        return "加速改善"
    if delta_1d > 0 and delta_5d > 3:
        return "缓慢改善"
    if abs(delta_1d) <= 2:
        return "钝化震荡"
    if delta_1d < -3 and delta_5d < -8:
        return "加速恶化"
    if delta_1d < 0 and delta_5d < -3:
        return "缓慢恶化"
    return "震荡"


def bounded_score(value: float) -> float:
    return max(0.0, min(100.0, float(value)))
