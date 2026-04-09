from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tradingagents.web.market_monitor_indicators import (
    atr_percent,
    bounded_score,
    latest_close,
    percent_change,
    rolling_percentile,
    slope_state,
    sma,
    zone_from_score,
)


LONG_TERM_ZONES = [
    (35, "防守区"),
    (50, "谨慎区"),
    (65, "试仓区"),
    (80, "进攻区"),
    (101, "强趋势区"),
]

SHORT_TERM_ZONES = [
    (20, "极差区"),
    (35, "弱势区"),
    (50, "观察区"),
    (65, "可做区"),
    (80, "活跃区"),
    (101, "高胜率区"),
]

SYSTEM_RISK_ZONES = [
    (20, "低压区"),
    (45, "正常区"),
    (60, "压力区"),
    (80, "高压区"),
    (101, "危机区"),
]


@dataclass
class ScoreSnapshot:
    score: float
    delta_1d: float
    delta_5d: float


def _series_to_scores(values: pd.Series) -> ScoreSnapshot:
    clean = values.dropna()
    if clean.empty:
        return ScoreSnapshot(50.0, 0.0, 0.0)
    score = bounded_score(clean.iloc[-1])
    delta_1d = float(clean.iloc[-1] - clean.iloc[-2]) if len(clean) > 1 else 0.0
    delta_5d = float(clean.iloc[-1] - clean.iloc[-6]) if len(clean) > 5 else delta_1d
    return ScoreSnapshot(score=score, delta_1d=delta_1d, delta_5d=delta_5d)


def build_long_term_series(core_data: dict[str, pd.DataFrame], breadth_ratio: pd.Series) -> pd.Series:
    spy = core_data["SPY"]["Close"].dropna()
    qqq = core_data["QQQ"]["Close"].dropna()
    vix = core_data.get("^VIX", pd.DataFrame()).get("Close", pd.Series(dtype=float)).dropna()

    aligned = pd.concat(
        {
            "spy": spy,
            "qqq": qqq,
            "breadth": breadth_ratio,
        },
        axis=1,
    ).dropna()
    if aligned.empty:
        return pd.Series(dtype=float)

    ma200 = sma(aligned["spy"], 200)
    ma50 = sma(aligned["spy"], 50)
    ma50_slope = ma50 - ma50.shift(20)
    range_low = aligned["spy"].rolling(63, min_periods=20).min()
    range_high = aligned["spy"].rolling(63, min_periods=20).max()
    vix_aligned = vix.reindex(aligned.index).ffill()

    score = pd.Series(0.0, index=aligned.index)
    score += ((aligned["spy"] - ma200) / ma200).clip(-0.05, 0.05).fillna(0) * 300
    score += expanding_percentile(ma50_slope.fillna(0)) * 0.2
    score += (((aligned["spy"] - range_low) / (range_high - range_low + 1e-9)) * 25).fillna(0)
    trend_sync = ((aligned["spy"].pct_change(20) > 0) & (aligned["qqq"].pct_change(20) > 0)).astype(float) * 15
    score += trend_sync.fillna(0)
    score += breadth_ratio.reindex(aligned.index).fillna(method="ffill").fillna(0) * 0.25
    if not vix_aligned.empty:
        score += (100 - expanding_percentile(vix_aligned)) * 0.15
    return score.apply(bounded_score)


def build_short_term_series(
    core_data: dict[str, pd.DataFrame],
    sector_data: dict[str, pd.DataFrame],
    breadth_ratio: pd.Series,
) -> pd.Series:
    spy = core_data["SPY"]["Close"].dropna()
    aligned = pd.DataFrame({"spy": spy}).dropna()
    if aligned.empty:
        return pd.Series(dtype=float)

    sector_momentum = []
    for frame in sector_data.values():
        close = frame.get("Close", pd.Series(dtype=float)).dropna()
        rel = close.pct_change(5) - close.pct_change(20)
        sector_momentum.append(rel.rename("sector"))
    sector_panel = pd.concat(sector_momentum, axis=1) if sector_momentum else pd.DataFrame(index=aligned.index)
    positive_ratio = (sector_panel > 0).mean(axis=1).reindex(aligned.index).fillna(0) * 100
    atr_pct = spy.pct_change().rolling(14).std() * 100 * 5
    atr_score = 100 - (atr_pct - 2.0).abs() * 25

    gap_quality = (
        core_data["SPY"]["Open"].reindex(aligned.index) - core_data["SPY"]["Close"].shift(1).reindex(aligned.index)
    ) / core_data["SPY"]["Close"].shift(1).reindex(aligned.index) * 100
    gap_score = (gap_quality > 0).rolling(5, min_periods=3).mean().fillna(0) * 100

    breadth_component = breadth_ratio.reindex(aligned.index).fillna(method="ffill").fillna(0)
    score = positive_ratio * 0.35 + bounded_score_series(atr_score) * 0.2 + gap_score * 0.15 + breadth_component * 0.3
    return score.apply(bounded_score)


def bounded_score_series(series: pd.Series) -> pd.Series:
    return series.fillna(50).apply(bounded_score)


def expanding_percentile(series: pd.Series, window: int = 252) -> pd.Series:
    result = pd.Series(index=series.index, dtype=float)
    clean = series.copy()
    for idx, (label, value) in enumerate(clean.items()):
        if pd.isna(value):
            result.loc[label] = 50.0
            continue
        history = clean.iloc[max(0, idx - window + 1) : idx + 1].dropna()
        if history.empty:
            result.loc[label] = 50.0
        else:
            result.loc[label] = float((history <= value).mean() * 100.0)
    return result.fillna(50.0)


def build_system_risk_series(core_data: dict[str, pd.DataFrame], breadth_ratio: pd.Series) -> pd.Series:
    spy = core_data["SPY"]["Close"].dropna()
    iwm = core_data["IWM"]["Close"].dropna()
    xlu = core_data["XLU"]["Close"].dropna()
    vix = core_data.get("^VIX", pd.DataFrame()).get("Close", pd.Series(dtype=float)).dropna()

    aligned = pd.concat({"spy": spy, "iwm": iwm, "xlu": xlu}, axis=1).dropna()
    if aligned.empty:
        return pd.Series(dtype=float)

    iwm_rel = ((aligned["iwm"].pct_change(5) - aligned["spy"].pct_change(5)) * -100).fillna(0)
    xlu_rel = ((aligned["xlu"].pct_change(5) - aligned["spy"].pct_change(5)) * 100).fillna(0)
    breadth_stress = (100 - breadth_ratio.reindex(aligned.index).fillna(method="ffill").fillna(50))
    score = iwm_rel.clip(-10, 10) * 2 + xlu_rel.clip(-10, 10) * 2 + breadth_stress * 0.35
    if not vix.empty:
        vix_aligned = vix.reindex(aligned.index).ffill().fillna(method="bfill")
        score += expanding_percentile(vix_aligned) * 0.35
    return score.apply(bounded_score)


def build_breadth_ratio(nasdaq_frames: dict[str, pd.DataFrame]) -> pd.Series:
    closes = []
    for symbol, frame in nasdaq_frames.items():
        close = frame.get("Close", pd.Series(dtype=float)).dropna()
        if close.empty:
            continue
        ma200 = sma(close, 200)
        closes.append((close > ma200).astype(float).rename(symbol))
    if not closes:
        return pd.Series(dtype=float)
    panel = pd.concat(closes, axis=1)
    return panel.mean(axis=1) * 100


def summarize_score(series: pd.Series, zones: list[tuple[float, str]]) -> dict[str, float | str]:
    snapshot = _series_to_scores(series)
    return {
        "score": snapshot.score,
        "zone": zone_from_score(snapshot.score, zones),
        "delta_1d": snapshot.delta_1d,
        "delta_5d": snapshot.delta_5d,
        "slope_state": slope_state(snapshot.delta_1d, snapshot.delta_5d),
    }


def score_tactic_layer(nasdaq_frames: dict[str, pd.DataFrame]) -> dict[str, float]:
    breakout_successes = []
    dip_buy_scores = []
    oversold_bounce_scores = []

    for frame in nasdaq_frames.values():
        close = frame.get("Close", pd.Series(dtype=float)).dropna()
        if len(close) < 30:
            continue
        rolling_high = close.rolling(20).max().shift(1)
        breakout = (close > rolling_high).astype(float)
        breakout_successes.append((breakout * close.pct_change(3).shift(-3).fillna(0) > 0).tail(10).mean())

        rolling_low = close.rolling(5).min().shift(1)
        dip_buy_scores.append(((close / rolling_low - 1).tail(10).mean()) if rolling_low.notna().any() else 0)

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        oversold_bounce_scores.append(close.pct_change(2).where(rsi < 30).tail(10).mean())

    breakout_score = bounded_score((pd.Series(breakout_successes).fillna(0).mean() or 0) * 100)
    dip_buy_score = bounded_score((pd.Series(dip_buy_scores).fillna(0).mean() or 0) * 500)
    oversold_score = bounded_score((pd.Series(oversold_bounce_scores).fillna(0).mean() or 0) * 800)
    return {
        "trend_breakout": breakout_score,
        "dip_buy": dip_buy_score,
        "oversold_bounce": oversold_score,
    }


def score_asset_layer(core_data: dict[str, pd.DataFrame]) -> dict[str, float]:
    spy = core_data["SPY"]["Close"].dropna()
    if len(spy) < 11:
        return {
            "large_cap_tech": 50.0,
            "small_cap_momentum": 50.0,
            "defensive": 50.0,
            "energy_cyclical": 50.0,
            "financials": 50.0,
        }

    def relative_score(symbol: str) -> float:
        close = core_data[symbol]["Close"].dropna()
        if len(close) < 11 or spy.empty:
            return 50.0
        rel = percent_change(close, 10) - percent_change(spy, 10)
        return bounded_score(50 + rel * 4)

    if any(len(core_data[symbol]["Close"].dropna()) < 11 for symbol in ["XLU", "XLV", "XLP", "XLE", "XLB"]):
        defensive_rel = 0.0
        energy_cycle_rel = 0.0
    else:
        defensive_close = (
            core_data["XLU"]["Close"].dropna().pct_change(10).iloc[-1]
            + core_data["XLV"]["Close"].dropna().pct_change(10).iloc[-1]
            + core_data["XLP"]["Close"].dropna().pct_change(10).iloc[-1]
        ) / 3
        defensive_rel = defensive_close - spy.pct_change(10).dropna().iloc[-1]

        energy_cycle_rel = (
            core_data["XLE"]["Close"].dropna().pct_change(10).iloc[-1]
            + core_data["XLB"]["Close"].dropna().pct_change(10).iloc[-1]
        ) / 2 - spy.pct_change(10).dropna().iloc[-1]

    return {
        "large_cap_tech": relative_score("QQQ"),
        "small_cap_momentum": relative_score("IWM"),
        "defensive": bounded_score(50 + defensive_rel * 400),
        "energy_cyclical": bounded_score(50 + energy_cycle_rel * 400),
        "financials": relative_score("XLF"),
    }
