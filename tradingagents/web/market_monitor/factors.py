from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import re
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from .data import _expected_market_close_date
from .indicators import (
    _column_series,
    atr_percent,
    benefit_score_slope_state,
    bounded_score,
    percent_change,
    risk_score_slope_state,
    rolling_percentile,
    sma,
    zone_from_score,
)
from .schemas import (
    MarketMonitorActionModifier,
    MarketMonitorEventFact,
    MarketMonitorEventRiskFlag,
    MarketMonitorEventTrigger,
    MarketMonitorExecutionCard,
    MarketMonitorFactorBreakdown,
    MarketMonitorIndexEventRisk,
    MarketMonitorInputDataStatus,
    MarketMonitorLayerMetric,
    MarketMonitorMissingDataItem,
    MarketMonitorPanicCard,
    MarketMonitorScoreCard,
    MarketMonitorSignalConfirmation,
    MarketMonitorSnapshotResponse,
    MarketMonitorStockEventRisk,
    MarketMonitorStyleAssetLayer,
    MarketMonitorStyleEffectiveness,
    MarketMonitorStyleTacticLayer,
    MarketMonitorSystemRiskCard,
)


@dataclass(frozen=True)
class MarketMonitorInputBundle:
    as_of_date: date
    timestamp: datetime
    core_data: dict[str, pd.DataFrame]
    cache_summary: dict[str, Any]
    universe: dict[str, list[str]]
    data_mode: str
    data_freshness: str
    input_data_status: MarketMonitorInputDataStatus
    missing_data: list[MarketMonitorMissingDataItem]
    risks: list[str]
    event_fact_candidates: list[Any]


CORE_REQUIRED_SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "^VIX", "LQD", "JNK"]


def build_input_bundle(
    *,
    as_of_date: date,
    dataset: dict[str, Any],
    universe: dict[str, list[str]],
    timestamp: datetime | None = None,
) -> MarketMonitorInputBundle:
    generated_at = timestamp or datetime.now(timezone.utc)
    core_data = dataset["core"]
    cache_summary = dataset.get("cache_summary", {})
    available = [symbol for symbol in CORE_REQUIRED_SYMBOLS if _has_close(core_data.get(symbol, pd.DataFrame()))]
    missing = [symbol for symbol in CORE_REQUIRED_SYMBOLS if symbol not in available]
    stale_symbols = [
        item["symbol"]
        for item in cache_summary.get("symbols", [])
        if item.get("result_state") == "stale_fallback"
    ]
    empty_symbols = [
        item["symbol"]
        for item in cache_summary.get("symbols", [])
        if item.get("result_state") == "empty"
    ]
    today = date.today()
    expected_close = _expected_market_close_date(as_of_date).date()
    data_freshness = "daily_final" if as_of_date < today else "daily_partial"
    if expected_close < as_of_date:
        data_freshness = "previous_trading_day"
    status = MarketMonitorInputDataStatus(
        core_symbols_available=available,
        core_symbols_missing=missing,
        interval="1d",
        includes_prepost=False,
        source="yfinance",
        stale_symbols=stale_symbols,
        partial_symbols=[] if data_freshness != "daily_partial" else available,
    )
    missing_data = [
        MarketMonitorMissingDataItem(
            field=f"symbol.{symbol}",
            reason="yfinance 未返回可用日线数据",
            impact="相关因子使用缺失标记并降低置信度",
            severity="high" if symbol in {"SPY", "QQQ", "IWM", "^VIX"} else "medium",
        )
        for symbol in missing
    ]
    risks = []
    if missing:
        risks.append(f"核心行情缺失: {', '.join(missing)}")
    if stale_symbols:
        risks.append(f"部分标的使用 stale fallback: {', '.join(stale_symbols)}")
    if empty_symbols:
        risks.append(f"部分标的无可用日线: {', '.join(empty_symbols)}")
    return MarketMonitorInputBundle(
        as_of_date=as_of_date,
        timestamp=generated_at,
        core_data=core_data,
        cache_summary=cache_summary,
        universe=universe,
        data_mode="daily",
        data_freshness=data_freshness,
        input_data_status=status,
        missing_data=missing_data,
        risks=risks,
        event_fact_candidates=_event_fact_candidates_from_dataset(dataset),
    )


def build_event_fact_sheet(bundle: MarketMonitorInputBundle) -> list[MarketMonitorEventFact]:
    events: list[MarketMonitorEventFact] = []
    for candidate in bundle.event_fact_candidates:
        event = _normalize_event_fact(candidate, bundle)
        if event is not None and event.expires_at > bundle.timestamp:
            events.append(event)
    return _dedupe_event_facts(events)[:20]


def _event_fact_candidates_from_dataset(dataset: dict[str, Any]) -> list[Any]:
    candidates: list[Any] = []
    for key in ("event_fact_candidates", "event_facts", "event_fact_sheet"):
        value = dataset.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    search = dataset.get("search")
    if isinstance(search, dict):
        value = search.get("event_fact_candidates") or search.get("event_facts")
        if isinstance(value, list):
            candidates.extend(value)
    return candidates


def _normalize_event_fact(candidate: Any, bundle: MarketMonitorInputBundle) -> MarketMonitorEventFact | None:
    if isinstance(candidate, MarketMonitorEventFact):
        payload = candidate.model_dump()
    elif isinstance(candidate, dict):
        payload = dict(candidate)
    else:
        return None
    event = _clean_text(payload.get("event"))
    source_name = _clean_text(payload.get("source_name"))
    source_summary = _clean_text(payload.get("source_summary"))
    if not event or not source_name or not source_summary:
        return None
    observed_at = _parse_event_datetime(payload.get("observed_at"), bundle.timestamp)
    expires_at = _parse_event_datetime(payload.get("expires_at"), _default_event_expiry(observed_at))
    source_url = _normalize_source_url(payload.get("source_url"))
    if payload.get("source_url") and source_url is None:
        return None
    source_type = _clean_text(payload.get("source_type")) or "unknown"
    confidence = _clamp_float(payload.get("confidence"), 0.55)
    confidence = min(confidence, _source_confidence_cap(source_type, source_name, source_url))
    scope = _normalize_scope(payload.get("scope"))
    severity = _normalize_severity(payload.get("severity"))
    time_window = _clean_text(payload.get("time_window")) or _derive_time_window(bundle.timestamp, expires_at)
    event_id = _clean_text(payload.get("event_id")) or _event_fact_id(
        event=event,
        scope=scope,
        time_window=time_window,
        source_name=source_name,
        observed_at=observed_at,
    )
    return MarketMonitorEventFact(
        event_id=event_id,
        event=event,
        scope=scope,
        time_window=time_window,
        severity=severity,
        source_type=source_type,
        source_name=source_name,
        source_url=source_url,
        source_summary=source_summary,
        observed_at=observed_at,
        confidence=round(confidence, 2),
        expires_at=expires_at,
    )


def _dedupe_event_facts(events: list[MarketMonitorEventFact]) -> list[MarketMonitorEventFact]:
    deduped: dict[tuple[str, str, str], MarketMonitorEventFact] = {}
    for event in events:
        key = (_event_key_text(event.event), event.scope, event.time_window)
        current = deduped.get(key)
        if current is None or (event.confidence, event.observed_at) > (current.confidence, current.observed_at):
            deduped[key] = event
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(
        deduped.values(),
        key=lambda item: (severity_rank.get(item.severity, 9), item.expires_at, -item.confidence, item.event),
    )


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _event_key_text(value: str) -> str:
    return re.sub(r"[^a-z0-9一-鿿]+", " ", value.lower()).strip()


def _normalize_scope(value: Any) -> str:
    allowed = {"index_level", "stock_level", "sector_level", "cross_asset", "unknown"}
    text = _clean_text(value)
    return text if text in allowed else "unknown"


def _normalize_severity(value: Any) -> str:
    text = _clean_text(value).lower()
    aliases = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "normal": "medium",
        "low": "low",
    }
    return aliases.get(text, "medium")


def _parse_event_datetime(value: Any, default: datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max, tzinfo=timezone.utc)
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = default
    else:
        parsed = default
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _default_event_expiry(observed_at: datetime) -> datetime:
    return observed_at + timedelta(days=1)


def _derive_time_window(observed_at: datetime, expires_at: datetime) -> str:
    if expires_at.date() == observed_at.date():
        return "today"
    if expires_at.date() == (observed_at + timedelta(days=1)).date():
        return "next_24h"
    return "active_window"


def _normalize_source_url(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return text


def _source_confidence_cap(source_type: str, source_name: str, source_url: str | None) -> float:
    text = f"{source_type} {source_name}".lower()
    if any(token in text for token in ("official", "calendar", "exchange", "issuer", "filing", "federal", "bls")):
        return 0.95
    if any(token in text for token in ("reuters", "bloomberg", "cnbc", "wsj", "marketwatch", "news")):
        return 0.85
    if source_url:
        return 0.70
    return 0.55


def _clamp_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))


def _event_fact_id(*, event: str, scope: str, time_window: str, source_name: str, observed_at: datetime) -> str:
    basis = "|".join([_event_key_text(event), scope, time_window, source_name.lower(), observed_at.date().isoformat()])
    return f"event-{hashlib.sha256(basis.encode('utf-8')).hexdigest()[:12]}"


def build_long_term_card(bundle: MarketMonitorInputBundle) -> MarketMonitorScoreCard:
    data = bundle.core_data
    spy = _close(data, "SPY")
    qqq = _close(data, "QQQ")
    iwm = _close(data, "IWM")
    dia = _close(data, "DIA")
    vix = _close(data, "^VIX")
    lqd = _close(data, "LQD")
    jnk = _close(data, "JNK")
    sectors = [_close(data, symbol) for symbol in bundle.universe["sector_etfs"]]
    xlu = _close(data, "XLU")
    xlp = _close(data, "XLP")
    xlv = _close(data, "XLV")
    distance = _ma_distance(spy, 200)
    ma50_slope = _ma_slope(spy, 50, 20)
    range_pos = _range_position(spy, 63)
    sync_score = 100.0 if percent_change(spy, 20) > 0 and percent_change(qqq, 20) > 0 else 45.0 if percent_change(spy, 20) * percent_change(qqq, 20) >= 0 else 25.0
    core_above = _above_ma_count([spy, qqq, iwm, dia], 50) * 50.0 + _above_ma_count([spy, qqq, iwm, dia], 200) * 50.0
    sector_positive = _positive_ratio(sectors, 5) * 50.0 + _above_ma_ratio(sectors, 50) * 50.0
    offense = (percent_change(qqq, 10) + percent_change(iwm, 10)) / 2
    defense = (percent_change(xlu, 10) + percent_change(xlp, 10) + percent_change(xlv, 10)) / 3
    qqq_rel = percent_change(qqq, 10) - percent_change(spy, 10)
    iwm_rel = percent_change(iwm, 10) - percent_change(spy, 10)
    cyclical = _relative_group(data, ["XLE", "XLB", "XLF"], "SPY", 10)
    vix_level = float(vix.iloc[-1]) if not vix.empty else None
    vix_percentile = rolling_percentile(vix, vix_level) if vix_level is not None else 50.0
    vix_change_5d = percent_change(vix, 5)
    credit = (percent_change(jnk, 10) - percent_change(lqd, 10) + percent_change(jnk, 10) - percent_change(spy, 10)) / 2
    factors = [
        _factor("spy_ma200_distance", distance, "pct", None, "higher_is_better", bounded_score(50 + distance * 5), 0.12, "SPY 相对 200 日均线位置决定长线趋势背景。"),
        _factor("spy_ma50_slope", ma50_slope, "pct", None, "higher_is_better", bounded_score(50 + ma50_slope * 8), 0.08, "50 日均线斜率反映中期趋势惯性。"),
        _factor("spy_3m_range_position", range_pos, "pct", None, "higher_is_better", range_pos, 0.08, "SPY 三个月区间位置越高，长线环境越友好。"),
        _factor("qqq_spy_sync", sync_score, "score", None, "higher_is_better", sync_score, 0.08, "QQQ 与 SPY 同向上升代表趋势同步性更好。"),
        _factor("core_risk_asset_breadth", core_above, "score", None, "higher_is_better", core_above, 0.12, "核心宽基 ETF 站上均线数量越多，广度越友好。"),
        _factor("sector_breadth", sector_positive, "score", None, "higher_is_better", sector_positive, 0.13, "行业 ETF 5日为正和站上 MA50 的比例代表广度修复。"),
        _factor("offense_defense_spread", offense - defense, "pct", None, "higher_is_better", bounded_score(50 + (offense - defense) * 5), 0.10, "进攻板块相对防御板块越强，风险偏好越友好。"),
        _factor("qqq_leadership", qqq_rel, "pct", None, "higher_is_better", bounded_score(50 + qqq_rel * 8), 0.05, "大盘科技相对 SPY 的 10 日动量代表龙头确认。"),
        _factor("iwm_confirmation", iwm_rel, "pct", None, "higher_is_better", bounded_score(50 + iwm_rel * 8), 0.05, "小盘相对 SPY 走强代表风险偏好扩散。"),
        _factor("cyclical_participation", cyclical, "pct", None, "higher_is_better", bounded_score(50 + cyclical * 8), 0.05, "周期板块相对 SPY 参与度越高越友好。"),
        _factor("vix_level_health", vix_level, "index_points", vix_percentile, "lower_is_better", 100 - vix_percentile, 0.07, "VIX 分位越高，波动健康度越差。", data_status="available" if vix_level is not None else "missing"),
        _factor("vix_trend_health", vix_change_5d, "pct", None, "lower_is_better", bounded_score(55 - vix_change_5d * 2), 0.04, "VIX 快速抬升会压低长线健康度。"),
        _factor("credit_risk_proxy", credit, "pct", None, "higher_is_better", bounded_score(50 + credit * 8), 0.03, "JNK 相对 LQD/SPY 越强，信用风险偏好越好。"),
    ]
    score = _weighted_score(factors)
    delta_1d = _rolling_score_delta(spy, 1)
    delta_5d = _rolling_score_delta(spy, 5)
    zone = zone_from_score(score, [(35, "防守区"), (50, "谨慎区"), (65, "试仓区"), (80, "进攻区"), (101, "强趋势区")])
    return MarketMonitorScoreCard(
        deterministic_score=round(score, 1),
        score=round(score, 1),
        zone=zone,
        delta_1d=round(delta_1d, 1),
        delta_5d=round(delta_5d, 1),
        slope_state=benefit_score_slope_state(delta_1d, delta_5d),
        recommended_exposure=_long_term_exposure(score),
        factor_breakdown=factors,
        confidence=_confidence(bundle, factors),
        key_drivers=_top_factor_reasons(factors),
        risks=_card_risks(bundle, factors),
    )


def build_short_term_card(bundle: MarketMonitorInputBundle) -> MarketMonitorScoreCard:
    data = bundle.core_data
    spy = _close(data, "SPY")
    qqq = _close(data, "QQQ")
    iwm = _close(data, "IWM")
    vix = _close(data, "^VIX")
    sectors = [_close(data, symbol) for symbol in bundle.universe["sector_etfs"]]
    sector_continuity = sum(1 for series in sectors if percent_change(series, 5) > percent_change(series, 20) * 0.25) / len(sectors) * 100 if sectors else 50.0
    rotation_stability = 100 - min(100, _dispersion([percent_change(series, 5) for series in sectors]) * 10)
    breakout = _breakout_persistence([spy, qqq, iwm] + sectors)
    hold_breakout = _positive_ratio([spy, qqq, iwm], 5) * 100
    high_beta = _relative_group(data, ["ARKK", "IWM", "XLE", "XLF"], "SPY", 5)
    defense = _relative_group(data, ["XLU", "XLP", "XLV"], "SPY", 5)
    atr = atr_percent(data.get("SPY", pd.DataFrame()))
    vix_change = (percent_change(vix, 1) + percent_change(vix, 5)) / 2
    factors = [
        _factor("sector_5d_vs_20d_momentum", sector_continuity, "pct", None, "higher_is_better", sector_continuity, 0.18, "行业 ETF 5日超额动量扩散越广，热点延续性越强。"),
        _factor("sector_rotation_stability", rotation_stability, "score", None, "higher_is_better", rotation_stability, 0.12, "领先行业强弱顺序越稳定，短线可交易性越好。"),
        _factor("etf_breakout_persistence", breakout, "score", None, "higher_is_better", breakout, 0.15, "主要 ETF 突破近20日高点后的延续情况。"),
        _factor("etf_breakout_hold", hold_breakout, "score", None, "higher_is_better", hold_breakout, 0.10, "核心 ETF 近期正收益代表突破守住率 proxy。"),
        _factor("high_beta_participation", high_beta, "pct", None, "higher_is_better", bounded_score(50 + high_beta * 10), 0.15, "高 Beta / 周期风格同步改善支持短线进攻。"),
        _factor("defensive_suppression", defense, "pct", None, "higher_is_riskier", bounded_score(55 - defense * 10), 0.10, "防御板块跑赢越明显，短线进攻环境越差。"),
        _factor("spy_atr_friendliness", atr, "pct", None, "middle_is_better", bounded_score(100 - abs(atr - 1.8) * 24), 0.10, "ATR 过低或过高都会降低短线交易友好度。"),
        _factor("vix_change_friendliness", vix_change, "pct", None, "lower_is_better", bounded_score(55 - vix_change * 3), 0.10, "VIX 1日/5日快速抬升会压低短线分。"),
    ]
    score = _weighted_score(factors)
    delta_1d = _rolling_score_delta(spy, 1, 1.6)
    delta_5d = _rolling_score_delta(spy, 5, 2.4)
    zone = zone_from_score(score, [(20, "极差区"), (35, "弱势区"), (50, "观察区"), (65, "可做区"), (80, "活跃区"), (101, "高胜率区")])
    return MarketMonitorScoreCard(
        deterministic_score=round(score, 1),
        score=round(score, 1),
        zone=zone,
        delta_1d=round(delta_1d, 1),
        delta_5d=round(delta_5d, 1),
        slope_state=benefit_score_slope_state(delta_1d, delta_5d),
        factor_breakdown=factors,
        confidence=_confidence(bundle, factors),
        key_drivers=_top_factor_reasons(factors),
        risks=_card_risks(bundle, factors),
    )


def build_system_risk_card(bundle: MarketMonitorInputBundle, event_fact_sheet: list[MarketMonitorEventFact]) -> MarketMonitorSystemRiskCard:
    data = bundle.core_data
    spy = _close(data, "SPY")
    qqq = _close(data, "QQQ")
    iwm = _close(data, "IWM")
    arkk = _close(data, "ARKK")
    xlu = _close(data, "XLU")
    lqd = _close(data, "LQD")
    jnk = _close(data, "JNK")
    vix = _close(data, "^VIX")
    vix_level = float(vix.iloc[-1]) if not vix.empty else None
    vix_percentile = rolling_percentile(vix, vix_level) if vix_level is not None else 50.0
    vix_5d = percent_change(vix, 5)
    lqd_trend = _ma_distance(lqd, 50)
    jnk_lqd = percent_change(jnk, 5) - percent_change(lqd, 5)
    jnk_spy = percent_change(jnk, 5) - percent_change(spy, 5)
    iwm_rel = percent_change(iwm, 5) - percent_change(spy, 5)
    xlu_rel = percent_change(xlu, 5) - percent_change(spy, 5)
    arkk_rel = percent_change(arkk, 5) - percent_change(spy, 5)
    sync_down = sum(1 for series in [spy, qqq, iwm, jnk] if percent_change(series, 5) < 0) / 4 * 100
    liquidity_factors = [
        _factor("vix_level", vix_level, "index_points", vix_percentile, "higher_is_riskier", vix_percentile, 0.35, "VIX 252日分位越高，系统风险越高。", data_status="available" if vix_level is not None else "missing"),
        _factor("vix_rise_speed", vix_5d, "pct", None, "higher_is_riskier", bounded_score(50 + vix_5d * 2), 0.20, "VIX 5日快速抬升代表流动性压力上升。"),
        _factor("lqd_trend_pressure", lqd_trend, "pct", None, "lower_is_better", bounded_score(50 - lqd_trend * 8), 0.20, "LQD 跌破趋势代表投资级信用代理承压。"),
        _factor("hy_credit_pressure", (jnk_lqd + jnk_spy) / 2, "pct", None, "lower_is_better", bounded_score(50 - (jnk_lqd + jnk_spy) * 5), 0.25, "JNK 相对 LQD/SPY 走弱代表高收益信用承压。"),
    ]
    appetite_factors = [
        _factor("iwm_spy_relative_weakness", iwm_rel, "pct", None, "lower_is_better", bounded_score(50 - iwm_rel * 8), 0.30, "IWM 相对 SPY 越弱，风险偏好越差。"),
        _factor("xlu_spy_defensive_strength", xlu_rel, "pct", None, "higher_is_riskier", bounded_score(50 + xlu_rel * 8), 0.25, "XLU 相对 SPY 越强，避险偏好越强。"),
        _factor("arkk_spy_relative_weakness", arkk_rel, "pct", None, "lower_is_better", bounded_score(50 - arkk_rel * 7), 0.20, "ARKK 相对走弱代表高 Beta 风险偏好下降。"),
        _factor("cross_asset_sync_down", sync_down, "pct", None, "higher_is_riskier", sync_down, 0.25, "SPY/QQQ/IWM/JNK 同步走弱越多，系统风险越高。"),
    ]
    liquidity = _weighted_score(liquidity_factors)
    appetite = _weighted_score(appetite_factors)
    factors = liquidity_factors + appetite_factors
    score = bounded_score(liquidity * 0.5 + appetite * 0.5)
    event_triggers = _system_event_triggers(vix, event_fact_sheet, bundle.timestamp)
    delta_1d = _rolling_score_delta(vix, 1, 2.2)
    delta_5d = _rolling_score_delta(vix, 5, 3.1)
    zone = zone_from_score(score, [(20, "低压区"), (45, "正常区"), (60, "压力区"), (70, "高压预警区"), (80, "高压区"), (101, "危机区")])
    return MarketMonitorSystemRiskCard(
        deterministic_score=round(score, 1),
        score=round(score, 1),
        zone=zone,
        delta_1d=round(delta_1d, 1),
        delta_5d=round(delta_5d, 1),
        slope_state=risk_score_slope_state(delta_1d, delta_5d),
        factor_breakdown=factors,
        liquidity_stress_score=round(liquidity, 1),
        risk_appetite_score=round(appetite, 1),
        event_triggers=event_triggers,
        confidence=_confidence(bundle, factors),
        key_drivers=_top_factor_reasons(factors),
        risks=_card_risks(bundle, factors),
    )


def build_style_effectiveness(bundle: MarketMonitorInputBundle) -> MarketMonitorStyleEffectiveness:
    data = bundle.core_data
    trend = _layer_metric("trend_breakout", _breakout_persistence([_close(data, symbol) for symbol in ["SPY", "QQQ", "IWM"] + bundle.universe["sector_etfs"]]), 0.0, "主要 ETF 突破后的延续表现。")
    dip_delta = percent_change(_close(data, "SPY"), 5)
    dip = _layer_metric("dip_buy", bounded_score(55 + dip_delta * 5), dip_delta, "SPY 回调后的近期修复表现。")
    oversold_delta = (percent_change(_close(data, "IWM"), 5) + percent_change(_close(data, "ARKK"), 5)) / 2
    oversold = _layer_metric("oversold_bounce", bounded_score(55 + oversold_delta * 6), oversold_delta, "高 Beta proxy basket 急跌后的修复强度。")
    tactic_pairs = {"趋势突破": trend.score, "回调低吸": dip.score, "超跌反弹": oversold.score}
    asset_metrics = {
        "large_cap_tech": _relative_layer_metric(data, "large_cap_tech", ["QQQ"], "SPY", "大盘科技相对 SPY 10日动量。"),
        "small_cap_momentum": _relative_layer_metric(data, "small_cap_momentum", ["IWM"], "SPY", "小盘高弹性相对 SPY 10日动量。"),
        "defensive": _relative_layer_metric(data, "defensive", ["XLU", "XLV", "XLP"], "SPY", "防御板块相对 SPY 10日动量。"),
        "energy_cyclical": _relative_layer_metric(data, "energy_cyclical", ["XLE", "XLB"], "SPY", "能源/周期相对 SPY 10日动量。"),
        "financials": _relative_layer_metric(data, "financials", ["XLF"], "SPY", "金融相对 SPY 10日动量。"),
    }
    asset_names = {
        "large_cap_tech": "大盘科技",
        "small_cap_momentum": "小盘高弹性",
        "defensive": "防御板块",
        "energy_cyclical": "能源/周期",
        "financials": "金融",
    }
    preferred_assets = [asset_names[key] for key, metric in asset_metrics.items() if metric.score >= 60]
    avoid_assets = [asset_names[key] for key, metric in asset_metrics.items() if metric.score < 45]
    all_factors = trend.factor_breakdown + dip.factor_breakdown + oversold.factor_breakdown
    all_factors += [factor for metric in asset_metrics.values() for factor in metric.factor_breakdown]
    return MarketMonitorStyleEffectiveness(
        tactic_layer=MarketMonitorStyleTacticLayer(
            trend_breakout=trend,
            dip_buy=dip,
            oversold_bounce=oversold,
            top_tactic=max(tactic_pairs, key=tactic_pairs.get),
            avoid_tactic=min(tactic_pairs, key=tactic_pairs.get),
        ),
        asset_layer=MarketMonitorStyleAssetLayer(
            large_cap_tech=asset_metrics["large_cap_tech"],
            small_cap_momentum=asset_metrics["small_cap_momentum"],
            defensive=asset_metrics["defensive"],
            energy_cyclical=asset_metrics["energy_cyclical"],
            financials=asset_metrics["financials"],
            preferred_assets=preferred_assets,
            avoid_assets=avoid_assets,
            factor_breakdown=all_factors,
        ),
        confidence=_confidence(bundle, all_factors),
        key_drivers=_top_factor_reasons(all_factors),
        risks=bundle.risks,
    )


def build_panic_card(
    bundle: MarketMonitorInputBundle,
    system_risk_score: float,
    previous_snapshots: list[MarketMonitorSnapshotResponse] | None = None,
) -> MarketMonitorPanicCard:
    data = bundle.core_data
    spy = data.get("SPY", pd.DataFrame())
    qqq = data.get("QQQ", pd.DataFrame())
    iwm = data.get("IWM", pd.DataFrame())
    dia = data.get("DIA", pd.DataFrame())
    arkk = data.get("ARKK", pd.DataFrame())
    vix = _close(data, "^VIX")
    proxy_drops = [abs(min(0.0, percent_change(_column_series(frame, "Close"), 1))) for frame in [spy, qqq, iwm, dia]]
    vix_jump = max(0.0, percent_change(vix, 1)) if not vix.empty else 0.0
    high_beta_slump = abs(min(0.0, (percent_change(_column_series(arkk, "Close"), 1) + percent_change(_column_series(iwm, "Close"), 1)) / 2))
    system_delta_trigger = 25.0 if _rolling_score_delta(vix, 1, 2.2) > 8 else 0.0
    panic_extreme = bounded_score((30 if max(proxy_drops or [0]) > 2.5 else 0) + (25 if vix_jump > 20 else 0) + (20 if high_beta_slump > 2.5 else 0) + system_delta_trigger)
    recovery = _range_recovery(spy)
    leader_relief_count = sum(1 for frame in [iwm, arkk, data.get("XLE", pd.DataFrame()), data.get("XLF", pd.DataFrame())] if percent_change(_column_series(frame, "Close"), 1) > -1.0)
    vix_relief = bounded_score(50 - vix_jump * 2)
    selling_exhaustion = bounded_score(recovery * 0.35 + 50 * 0.20 + leader_relief_count / 4 * 100 * 0.25 + vix_relief * 0.20)
    prev_mid = _previous_midpoint(spy)
    spy_close = _last_close(spy)
    above_prev_mid = 100.0 if spy_close is not None and prev_mid is not None and spy_close > prev_mid else 0.0
    upper_half = 100.0 if recovery > 50 else 0.0
    beta_repair = bounded_score(50 + ((percent_change(_column_series(arkk, "Close"), 1) + percent_change(_column_series(iwm, "Close"), 1)) / 2) * 10)
    intraday_reversal = bounded_score(above_prev_mid * 0.35 + upper_half * 0.30 + beta_repair * 0.20 + 50 * 0.15)
    score = bounded_score(panic_extreme * 0.40 + selling_exhaustion * 0.30 + intraday_reversal * 0.30)
    if panic_extreme < 35:
        state = "无信号"
    elif score >= 50 and (selling_exhaustion >= 50 or intraday_reversal >= 60):
        state = "panic_confirmed"
    elif panic_extreme >= 80:
        state = "capitulation_watch"
    else:
        state = "panic_watch"
    zone = _panic_zone(state, panic_extreme, score)
    factors = [
        _factor("panic_extreme_score", panic_extreme, "score", None, "higher_is_riskier", panic_extreme, 0.40, "恐慌程度只代表抛压强度，不等于反转确认。"),
        _factor("selling_exhaustion_score", selling_exhaustion, "score", None, "higher_is_better", selling_exhaustion, 0.30, "抛压衰竭迹象越充分，反弹确认条件越好。"),
        _factor("intraday_reversal_score", intraday_reversal, "score", None, "higher_is_better", intraday_reversal, 0.30, "日线模式下仅用当日/最近一根 OHLCV proxy 判断反弹确认。"),
    ]
    early_entry_allowed = state == "panic_confirmed" and intraday_reversal >= 60
    max_position_hint = _panic_position_hint(state, score, system_risk_score)
    refreshes_held = _panic_refreshes_held(state, previous_snapshots or [])
    return MarketMonitorPanicCard(
        score=round(score, 1),
        zone=zone,
        state=state,
        panic_extreme_score=round(panic_extreme, 1),
        selling_exhaustion_score=round(selling_exhaustion, 1),
        intraday_reversal_score=round(intraday_reversal, 1),
        factor_breakdown=factors,
        action=_panic_action(state, max_position_hint),
        system_risk_override="系统风险位于[80,100]时，反弹仓上限强制<=15%" if system_risk_score >= 80 else None,
        stop_loss="ATR*1.0",
        profit_rule="达1R兑现50%，余仓移止损至成本线",
        timeout_warning=refreshes_held > 5,
        refreshes_held=refreshes_held,
        early_entry_allowed=early_entry_allowed,
        max_position_hint=max_position_hint,
        confidence=_confidence(bundle, factors),
        risks=_card_risks(bundle, factors),
        key_drivers=_top_factor_reasons(factors),
    )


def build_execution_card(
    long_term: MarketMonitorScoreCard,
    short_term: MarketMonitorScoreCard,
    system_risk: MarketMonitorSystemRiskCard,
    style: MarketMonitorStyleEffectiveness,
    event_fact_sheet: list[MarketMonitorEventFact],
    panic: MarketMonitorPanicCard | None = None,
    previous_snapshots: list[MarketMonitorSnapshotResponse] | None = None,
) -> MarketMonitorExecutionCard:
    event_risk = _event_risk_flag(event_fact_sheet)
    if system_risk.score >= 80:
        regime_label = "红灯-危机"
        conflict_mode = "系统风险危机 override 生效"
        total_exposure_range = "0%-15%"
        new_position_allowed = False
        chase_breakout_allowed = False
        dip_buy_allowed = False
        overnight_allowed = False
        single_position_cap = "5%"
        daily_risk_budget = "0.25R"
    elif system_risk.score >= 70:
        regime_label = "红灯-高压"
        conflict_mode = "系统风险高压 override 生效"
        total_exposure_range = "0%-20%"
        new_position_allowed = False
        chase_breakout_allowed = False
        dip_buy_allowed = False
        overnight_allowed = False
        single_position_cap = "5%"
        daily_risk_budget = "0.25R"
    elif system_risk.score >= 60:
        regime_label = "橙灯"
        conflict_mode = "系统风险高压预警 override 生效"
        total_exposure_range = "20%-40%"
        new_position_allowed = False
        chase_breakout_allowed = False
        dip_buy_allowed = True
        overnight_allowed = False
        single_position_cap = "8%"
        daily_risk_budget = "0.5R"
    elif long_term.score >= 80 and short_term.score >= 65 and system_risk.score < 25:
        regime_label = "绿灯"
        conflict_mode = "长线强趋势+短线活跃+系统风险低"
        total_exposure_range = "80%-100%"
        new_position_allowed = True
        chase_breakout_allowed = True
        dip_buy_allowed = True
        overnight_allowed = True
        single_position_cap = "12%"
        daily_risk_budget = "1.0R"
    elif long_term.score >= 65 and short_term.score >= 55 and system_risk.score < 60:
        regime_label = "黄绿灯" if system_risk.score < 35 else "黄灯"
        conflict_mode = "长强短强，按系统风险强度控制进攻权限"
        total_exposure_range = "60%-80%"
        new_position_allowed = True
        chase_breakout_allowed = system_risk.score < 35
        dip_buy_allowed = True
        overnight_allowed = system_risk.score < 35
        single_position_cap = "10%"
        daily_risk_budget = "0.75R"
    elif 45 <= long_term.score < 65 and short_term.score >= 60 and system_risk.score < 35:
        regime_label = "黄绿灯-Swing"
        conflict_mode = "长线中性+短线强+系统风险低"
        total_exposure_range = "40%-60%"
        new_position_allowed = True
        chase_breakout_allowed = True
        dip_buy_allowed = True
        overnight_allowed = True
        single_position_cap = "10%"
        daily_risk_budget = "0.75R"
    elif long_term.score >= 65 and 25 <= short_term.score < 45:
        regime_label = "黄灯-等待"
        conflict_mode = "长线强但短线弱，趋势仓可保留，新开仓只允许低吸"
        total_exposure_range = "40%-60%"
        new_position_allowed = True
        chase_breakout_allowed = False
        dip_buy_allowed = True
        overnight_allowed = False
        single_position_cap = "8%"
        daily_risk_budget = "0.5R"
    elif long_term.score >= 65 and short_term.score < 25:
        regime_label = "橙灯"
        conflict_mode = "长线强但短线极差，趋势仓降风险并等待 panic 或短线修复"
        total_exposure_range = "20%-40%"
        new_position_allowed = False
        chase_breakout_allowed = False
        dip_buy_allowed = False
        overnight_allowed = False
        single_position_cap = "6%"
        daily_risk_budget = "0.5R"
    elif 45 <= long_term.score < 65 and 45 <= short_term.score < 55 and system_risk.score < 50:
        regime_label = "黄灯"
        conflict_mode = "长线中性+短线中性，低频操作并等待确认"
        total_exposure_range = "40%-60%"
        new_position_allowed = True
        chase_breakout_allowed = False
        dip_buy_allowed = True
        overnight_allowed = False
        single_position_cap = "8%"
        daily_risk_budget = "0.5R"
    elif long_term.score < 45 and short_term.score >= 55 and system_risk.score < 35:
        regime_label = "黄灯-短线"
        conflict_mode = "长线弱+短线强+系统风险低，只允许短线博弈仓"
        total_exposure_range = "20%-40%"
        new_position_allowed = True
        chase_breakout_allowed = False
        dip_buy_allowed = True
        overnight_allowed = False
        single_position_cap = "6%"
        daily_risk_budget = "0.5R"
    elif long_term.score < 45 and short_term.score < 45:
        regime_label = "红灯"
        conflict_mode = "长弱短弱，净值保护优先"
        total_exposure_range = "0%-20%"
        new_position_allowed = False
        chase_breakout_allowed = False
        dip_buy_allowed = False
        overnight_allowed = False
        single_position_cap = "5%"
        daily_risk_budget = "0.25R"
    elif short_term.score < 45:
        regime_label = "橙灯"
        conflict_mode = "短线弱，防守为主"
        total_exposure_range = "20%-40%"
        new_position_allowed = False
        chase_breakout_allowed = False
        dip_buy_allowed = True
        overnight_allowed = False
        single_position_cap = "8%"
        daily_risk_budget = "0.5R"
    else:
        regime_label = "黄灯"
        conflict_mode = "矩阵未完全覆盖，落入相邻更保守 regime"
        total_exposure_range = "40%-60%"
        new_position_allowed = True
        chase_breakout_allowed = False
        dip_buy_allowed = True
        overnight_allowed = True
        single_position_cap = "10%"
        daily_risk_budget = "0.75R"
    if event_risk.index_level.active and event_risk.index_level.action_modifier:
        modifier = event_risk.index_level.action_modifier
        if modifier.new_position_allowed is False:
            new_position_allowed = False
        if modifier.overnight_allowed is False:
            overnight_allowed = False
        if modifier.single_position_cap_multiplier is not None:
            single_position_cap = _apply_cap_multiplier(single_position_cap, modifier.single_position_cap_multiplier)
    execution_fields = {
        "regime_label": regime_label,
        "conflict_mode": conflict_mode,
        "total_exposure_range": total_exposure_range,
        "new_position_allowed": new_position_allowed,
        "chase_breakout_allowed": chase_breakout_allowed,
        "dip_buy_allowed": dip_buy_allowed,
        "overnight_allowed": overnight_allowed,
        "leverage_allowed": False,
        "single_position_cap": single_position_cap,
        "daily_risk_budget": daily_risk_budget,
    }
    execution_fields, signal_confirmation = _apply_signal_confirmation(execution_fields, previous_snapshots or [])
    risks = []
    if panic and panic.state == "panic_confirmed":
        risks.append("panic 仓位仅作为独立反弹策略仓，不代表趋势仓恢复。")
    return MarketMonitorExecutionCard(
        regime_label=execution_fields["regime_label"],
        conflict_mode=execution_fields["conflict_mode"],
        total_exposure_range=execution_fields["total_exposure_range"],
        new_position_allowed=execution_fields["new_position_allowed"],
        chase_breakout_allowed=execution_fields["chase_breakout_allowed"],
        dip_buy_allowed=execution_fields["dip_buy_allowed"],
        overnight_allowed=execution_fields["overnight_allowed"],
        leverage_allowed=execution_fields["leverage_allowed"],
        single_position_cap=execution_fields["single_position_cap"],
        daily_risk_budget=execution_fields["daily_risk_budget"],
        tactic_preference=f"{style.tactic_layer.top_tactic} > {style.tactic_layer.avoid_tactic}",
        preferred_assets=style.asset_layer.preferred_assets or ["现金"],
        avoid_assets=style.asset_layer.avoid_assets,
        signal_confirmation=signal_confirmation,
        event_risk_flag=event_risk,
        confidence=min(long_term.confidence, short_term.confidence, system_risk.confidence, style.confidence),
        risks=risks,
        key_drivers=[conflict_mode],
    )


def _apply_signal_confirmation(
    target: dict[str, Any],
    previous_snapshots: list[MarketMonitorSnapshotResponse],
) -> tuple[dict[str, Any], MarketMonitorSignalConfirmation]:
    previous_cards = [snapshot.execution_card for snapshot in previous_snapshots if snapshot.execution_card]
    previous_card = previous_cards[-1] if previous_cards else None
    target_signature = _execution_signature(target)
    observations = _consecutive_execution_observations(previous_cards, target_signature)
    if previous_card is None:
        return target, MarketMonitorSignalConfirmation(
            current_regime_observations=1,
            risk_loosening_unlock_in_observations=2,
            note="当前缺少上一轮执行状态；风险放宽需连续3次刷新保持后才放宽。",
        )
    if not _is_execution_loosening(target, previous_card):
        return target, MarketMonitorSignalConfirmation(
            current_regime_observations=observations,
            risk_loosening_unlock_in_observations=0,
            note="风险收紧当次生效；当前状态无需等待放宽确认。",
        )
    if "风险放宽确认中" in previous_card.conflict_mode and previous_card.conflict_mode.startswith(str(target["conflict_mode"])):
        observations = previous_card.signal_confirmation.current_regime_observations + 1
    remaining = max(0, 3 - observations)
    if remaining == 0:
        return target, MarketMonitorSignalConfirmation(
            current_regime_observations=observations,
            risk_loosening_unlock_in_observations=0,
            note="风险放宽已连续3次刷新确认，可解锁当前执行权限。",
        )
    locked = target | {
        "regime_label": previous_card.regime_label,
        "conflict_mode": f"{target['conflict_mode']}；风险放宽确认中，沿用上一轮更保守权限",
        "total_exposure_range": previous_card.total_exposure_range,
        "new_position_allowed": previous_card.new_position_allowed,
        "chase_breakout_allowed": previous_card.chase_breakout_allowed,
        "dip_buy_allowed": previous_card.dip_buy_allowed,
        "overnight_allowed": previous_card.overnight_allowed,
        "leverage_allowed": previous_card.leverage_allowed,
        "single_position_cap": previous_card.single_position_cap,
        "daily_risk_budget": previous_card.daily_risk_budget,
    }
    return locked, MarketMonitorSignalConfirmation(
        current_regime_observations=observations,
        risk_loosening_unlock_in_observations=remaining,
        note=f"风险放宽需连续3次刷新保持后才放宽；当前还需 {remaining} 次确认。",
    )


def _consecutive_execution_observations(
    previous_cards: list[MarketMonitorExecutionCard],
    target_signature: tuple[Any, ...],
) -> int:
    count = 1
    for card in reversed(previous_cards):
        if _execution_signature(card) != target_signature:
            break
        count += 1
    return count


def _execution_signature(value: Any) -> tuple[Any, ...]:
    if isinstance(value, dict):
        return (
            value["regime_label"],
            value["total_exposure_range"],
            value["new_position_allowed"],
            value["chase_breakout_allowed"],
            value["dip_buy_allowed"],
            value["overnight_allowed"],
            value["leverage_allowed"],
            value["single_position_cap"],
            value["daily_risk_budget"],
        )
    return (
        value.regime_label,
        value.total_exposure_range,
        value.new_position_allowed,
        value.chase_breakout_allowed,
        value.dip_buy_allowed,
        value.overnight_allowed,
        value.leverage_allowed,
        value.single_position_cap,
        value.daily_risk_budget,
    )


def _is_execution_loosening(target: dict[str, Any], previous: MarketMonitorExecutionCard) -> bool:
    if _range_max(target["total_exposure_range"]) > _range_max(previous.total_exposure_range):
        return True
    if _percent_value(target["single_position_cap"]) > _percent_value(previous.single_position_cap):
        return True
    if _risk_budget_value(target["daily_risk_budget"]) > _risk_budget_value(previous.daily_risk_budget):
        return True
    for field in ("new_position_allowed", "chase_breakout_allowed", "dip_buy_allowed", "overnight_allowed", "leverage_allowed"):
        if bool(target[field]) and not bool(getattr(previous, field)):
            return True
    return False


def _range_max(value: str) -> float:
    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    return float(numbers[-1]) if numbers else 0.0


def _percent_value(value: str) -> float:
    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    return float(numbers[0]) if numbers else 0.0


def _risk_budget_value(value: str) -> float:
    numbers = re.findall(r"\d+(?:\.\d+)?", value)
    return float(numbers[0]) if numbers else 0.0


def _panic_refreshes_held(state: str, previous_snapshots: list[MarketMonitorSnapshotResponse]) -> int:
    if state == "无信号":
        return 0
    count = 1
    for snapshot in reversed(previous_snapshots):
        if snapshot.panic_reversal_score.state != state:
            break
        count += 1
    return count


def _apply_cap_multiplier(single_position_cap: str, multiplier: float) -> str:
    try:
        cap_value = float(single_position_cap.rstrip("%"))
    except ValueError:
        return single_position_cap
    return f"{max(1.0, round(cap_value * multiplier)):.0f}%"


def _has_close(frame: pd.DataFrame) -> bool:
    return not _column_series(frame, "Close").empty


def _close(data: dict[str, pd.DataFrame], symbol: str) -> pd.Series:
    return _column_series(data.get(symbol, pd.DataFrame()), "Close")


def _last_close(frame: pd.DataFrame) -> float | None:
    close = _column_series(frame, "Close")
    return None if close.empty else float(close.iloc[-1])


def _ma_distance(series: pd.Series, window: int) -> float:
    ma = sma(series, window).dropna()
    if series.empty or ma.empty or ma.iloc[-1] == 0:
        return 0.0
    return float((series.iloc[-1] - ma.iloc[-1]) / ma.iloc[-1] * 100)


def _ma_slope(series: pd.Series, window: int, lookback: int) -> float:
    ma = sma(series, window).dropna()
    if len(ma) <= lookback or ma.iloc[-lookback - 1] == 0:
        return 0.0
    return float((ma.iloc[-1] - ma.iloc[-lookback - 1]) / ma.iloc[-lookback - 1] * 100)


def _range_position(series: pd.Series, window: int) -> float:
    clean = series.dropna().tail(window)
    if clean.empty:
        return 50.0
    low = float(clean.min())
    high = float(clean.max())
    if high == low:
        return 50.0
    return (float(clean.iloc[-1]) - low) / (high - low) * 100


def _range_recovery(frame: pd.DataFrame) -> float:
    high = _column_series(frame, "High")
    low = _column_series(frame, "Low")
    close = _column_series(frame, "Close")
    if high.empty or low.empty or close.empty:
        return 0.0
    latest_high = float(high.iloc[-1])
    latest_low = float(low.iloc[-1])
    if latest_high == latest_low:
        return 50.0
    return bounded_score((float(close.iloc[-1]) - latest_low) / (latest_high - latest_low) * 100)


def _previous_midpoint(frame: pd.DataFrame) -> float | None:
    high = _column_series(frame, "High")
    low = _column_series(frame, "Low")
    if len(high) < 2 or len(low) < 2:
        return None
    return float((high.iloc[-2] + low.iloc[-2]) / 2)


def _above_ma_count(series_list: list[pd.Series], window: int) -> float:
    if not series_list:
        return 0.0
    count = 0
    valid = 0
    for series in series_list:
        ma = sma(series, window).dropna()
        if series.empty or ma.empty:
            continue
        valid += 1
        count += 1 if series.iloc[-1] > ma.iloc[-1] else 0
    return count / valid if valid else 0.0


def _above_ma_ratio(series_list: list[pd.Series], window: int) -> float:
    return _above_ma_count(series_list, window) * 100


def _positive_ratio(series_list: list[pd.Series], periods: int) -> float:
    valid = [series for series in series_list if not series.empty]
    if not valid:
        return 0.5
    return sum(1 for series in valid if percent_change(series, periods) > 0) / len(valid)


def _relative_group(data: dict[str, pd.DataFrame], symbols: list[str], benchmark: str, periods: int) -> float:
    benchmark_change = percent_change(_close(data, benchmark), periods)
    changes = [percent_change(_close(data, symbol), periods) - benchmark_change for symbol in symbols]
    return sum(changes) / len(changes) if changes else 0.0


def _dispersion(values: list[float]) -> float:
    if not values:
        return 0.0
    avg = sum(values) / len(values)
    return sum(abs(value - avg) for value in values) / len(values)


def _breakout_persistence(series_list: list[pd.Series]) -> float:
    scores = []
    for series in series_list:
        clean = series.dropna()
        if len(clean) < 22:
            continue
        previous_high = float(clean.iloc[-21:-1].max())
        latest = float(clean.iloc[-1])
        if latest > previous_high:
            scores.append(100.0)
        elif percent_change(clean, 5) > 0:
            scores.append(65.0)
        else:
            scores.append(35.0)
    return sum(scores) / len(scores) if scores else 50.0


def _factor(
    factor: str,
    raw_value: float | str | bool | None,
    raw_value_unit: str | None,
    percentile: float | None,
    polarity: str,
    score: float,
    weight: float,
    reason: str,
    data_status: str = "available",
) -> MarketMonitorFactorBreakdown:
    return MarketMonitorFactorBreakdown(
        factor=factor,
        raw_value=None if isinstance(raw_value, float) and pd.isna(raw_value) else raw_value,
        raw_value_unit=raw_value_unit,
        percentile=percentile,
        polarity=polarity,
        score=round(bounded_score(score), 1),
        weight=weight,
        reason=reason,
        data_status=data_status,
    )


def _weighted_score(factors: list[MarketMonitorFactorBreakdown]) -> float:
    available = [factor for factor in factors if factor.data_status != "missing"]
    if not available:
        return 50.0
    weight_sum = sum(factor.weight for factor in available)
    if weight_sum <= 0:
        return 50.0
    return bounded_score(sum(factor.score * factor.weight for factor in available) / weight_sum)


def _confidence(bundle: MarketMonitorInputBundle, factors: list[MarketMonitorFactorBreakdown]) -> float:
    missing_factor_count = sum(1 for factor in factors if factor.data_status == "missing")
    missing_symbol_penalty = len(bundle.input_data_status.core_symbols_missing) * 0.06
    stale_penalty = len(bundle.input_data_status.stale_symbols) * 0.03
    factor_penalty = missing_factor_count * 0.05
    return round(max(0.35, min(0.92, 0.86 - missing_symbol_penalty - stale_penalty - factor_penalty)), 2)


def _card_risks(bundle: MarketMonitorInputBundle, factors: list[MarketMonitorFactorBreakdown]) -> list[str]:
    risks = list(bundle.risks)
    if any(factor.data_status == "missing" for factor in factors):
        risks.append("部分因子缺失，分数按可用 proxy 合成并降低置信度。")
    if not risks:
        risks.append("当前分数仅基于刷新当刻可得的 yfinance 日线与空事件事实表。")
    return list(dict.fromkeys(risks))


def _top_factor_reasons(factors: list[MarketMonitorFactorBreakdown]) -> list[str]:
    ranked = sorted(factors, key=lambda factor: factor.weight, reverse=True)
    return [factor.reason for factor in ranked[:3]]


def _rolling_score_delta(series: pd.Series, periods: int, multiplier: float = 1.0) -> float:
    return percent_change(series, periods) * multiplier


def _long_term_exposure(score: float) -> str:
    if score < 35:
        return "0%-20%"
    if score < 50:
        return "20%-40%"
    if score < 65:
        return "40%-60%"
    if score < 80:
        return "60%-80%"
    return "80%-100%"


def _system_event_triggers(
    vix: pd.Series,
    event_fact_sheet: list[MarketMonitorEventFact],
    observed_at: datetime,
) -> list[MarketMonitorEventTrigger]:
    triggers: list[MarketMonitorEventTrigger] = []
    vix_1d = percent_change(vix, 1)
    if vix_1d > 20:
        triggers.append(
            MarketMonitorEventTrigger(
                trigger_type="market_structure",
                event="VIX 单次刷新涨幅超过20%",
                severity="high",
                score_impact="+5",
                confidence=0.86,
                expires_at=observed_at + timedelta(days=1),
            )
        )
    for event in event_fact_sheet:
        if event.scope == "index_level" and event.severity in {"high", "critical"}:
            triggers.append(
                MarketMonitorEventTrigger(
                    trigger_type="event_fact",
                    event=event.event,
                    severity=event.severity,
                    score_impact="+5",
                    confidence=event.confidence,
                    expires_at=event.expires_at,
                    source_event_ids=[event.event_id],
                )
            )
    return triggers


def _layer_metric(name: str, score: float, delta_5d: float, reason: str) -> MarketMonitorLayerMetric:
    factor = _factor(name, score, "score", None, "higher_is_better", score, 1.0, reason)
    return MarketMonitorLayerMetric(score=round(score, 1), delta_5d=round(delta_5d, 1), valid=score >= 55, factor_breakdown=[factor])


def _relative_layer_metric(data: dict[str, pd.DataFrame], name: str, symbols: list[str], benchmark: str, reason: str) -> MarketMonitorLayerMetric:
    relative = _relative_group(data, symbols, benchmark, 10)
    score = bounded_score(50 + relative * 8)
    factor = _factor(name, relative, "pct", None, "higher_is_better", score, 1.0, reason)
    return MarketMonitorLayerMetric(score=round(score, 1), delta_5d=round(relative, 1), preferred=score >= 60, factor_breakdown=[factor])


def _event_risk_flag(event_fact_sheet: list[MarketMonitorEventFact]) -> MarketMonitorEventRiskFlag:
    index_events = [event for event in event_fact_sheet if event.scope == "index_level" and event.severity in {"high", "critical"}]
    stock_events = [event.event for event in event_fact_sheet if event.scope == "stock_level"]
    return MarketMonitorEventRiskFlag(
        index_level=MarketMonitorIndexEventRisk(
            active=bool(index_events),
            events=[event.event for event in index_events],
            source_event_ids=[event.event_id for event in index_events],
            action_modifier=MarketMonitorActionModifier(
                new_position_allowed=None,
                overnight_allowed=False,
                single_position_cap_multiplier=0.8,
                note="指数级高严重度事件触发隔夜与单票权限收紧。",
            ) if index_events else None,
        ),
        stock_level=MarketMonitorStockEventRisk(
            earnings_stocks=stock_events,
            rule="个股级事件只影响对应股票，不污染指数 regime。" if stock_events else None,
        ),
    )


def _panic_zone(state: str, panic_extreme: float, panic_reversal: float) -> str:
    if state == "无信号":
        return "无信号"
    if state == "panic_watch":
        return "观察期"
    if state == "capitulation_watch":
        return "投降观察"
    if panic_reversal < 65:
        return "一级试错"
    if panic_reversal < 80:
        return "二级反弹"
    return "强反转窗口"


def _panic_position_hint(state: str, score: float, system_risk_score: float) -> str:
    if state != "panic_confirmed":
        return "0%"
    if system_risk_score >= 80:
        return "<=15%"
    if score < 65:
        return "10%-20%"
    if score < 80:
        return "20%-35%"
    return "35%-50%"


def _panic_action(state: str, max_position_hint: str) -> str:
    if state == "panic_confirmed":
        return f"恐慌反弹确认，可按独立反弹策略仓试探，仓位提示 {max_position_hint}。"
    if state == "capitulation_watch":
        return "恐慌极端但未确认抛压衰竭，不默认抄底。"
    if state == "panic_watch":
        return "恐慌出现但尚不极端，加入观察，不执行。"
    return "无恐慌反转信号，不操作。"
