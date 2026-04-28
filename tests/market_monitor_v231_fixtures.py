from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from tradingagents.web.market_monitor.schemas import (
    MarketMonitorActionModifier,
    MarketMonitorDataStatusResponse,
    MarketMonitorEvidenceRef,
    MarketMonitorEventFact,
    MarketMonitorEventRiskFlag,
    MarketMonitorExecutionCard,
    MarketMonitorFactSheet,
    MarketMonitorFactorBreakdown,
    MarketMonitorHistoryPoint,
    MarketMonitorHistoryResponse,
    MarketMonitorIndexEventRisk,
    MarketMonitorInputDataStatus,
    MarketMonitorLayerMetric,
    MarketMonitorMissingDataItem,
    MarketMonitorPanicCard,
    MarketMonitorPromptTrace,
    MarketMonitorScoreAdjustment,
    MarketMonitorScoreCard,
    MarketMonitorSignalConfirmation,
    MarketMonitorSnapshotResponse,
    MarketMonitorStockEventRisk,
    MarketMonitorStyleAssetLayer,
    MarketMonitorStyleEffectiveness,
    MarketMonitorStyleTacticLayer,
    MarketMonitorSystemRiskCard,
)


def fixture_now() -> datetime:
    return datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)


def fixture_input_data_status() -> MarketMonitorInputDataStatus:
    return MarketMonitorInputDataStatus(
        core_symbols_available=["SPY", "QQQ", "IWM", "DIA", "^VIX"],
        core_symbols_missing=[],
        interval="1d",
        includes_prepost=False,
        source="yfinance",
        stale_symbols=[],
        partial_symbols=[],
    )


def fixture_missing_data() -> list[MarketMonitorMissingDataItem]:
    return [
        MarketMonitorMissingDataItem(
            field="event_fact_sheet",
            reason="当前刷新周期未注入联网搜索事件事实",
            impact="事件风险按空事实表处理",
            severity="medium",
        )
    ]


def fixture_risks() -> list[str]:
    return ["广度因子使用 ETF 代理池近似"]


def fixture_factor(name: str = "ETF proxy trend", *, polarity: str = "higher_is_better", score: float = 66.0) -> MarketMonitorFactorBreakdown:
    return MarketMonitorFactorBreakdown(
        factor=name,
        raw_value=1.8,
        raw_value_unit="%",
        percentile=64.0,
        polarity=polarity,
        score=score,
        weight=1.0,
        reason="核心 ETF 趋势保持正向。",
        data_status="available",
    )


def fixture_evidence() -> list[MarketMonitorEvidenceRef]:
    return [
        MarketMonitorEvidenceRef(
            source_type="local_market_data",
            source_label="SPY 日线",
            snippet="SPY close 523.1",
            confidence=0.9,
        )
    ]


def fixture_event_fact() -> MarketMonitorEventFact:
    now = fixture_now()
    return MarketMonitorEventFact(
        event_id="event-1",
        event="宏观数据窗口",
        scope="index_level",
        time_window="未来 1 日",
        severity="medium",
        source_type="calendar",
        source_name="test calendar",
        source_url=None,
        source_summary="未来一日可能出现宏观数据扰动。",
        observed_at=now,
        confidence=0.7,
        expires_at=now + timedelta(days=1),
    )


def fixture_event_risk_flag(active: bool = True) -> MarketMonitorEventRiskFlag:
    return MarketMonitorEventRiskFlag(
        index_level=MarketMonitorIndexEventRisk(
            active=active,
            events=["宏观数据窗口"] if active else [],
            source_event_ids=["event-1"] if active else [],
            action_modifier=MarketMonitorActionModifier(note="减少追高。" if active else "当前无指数级事件修正。"),
        ),
        stock_level=MarketMonitorStockEventRisk(
            earnings_stocks=["NVDA"] if active else [],
            rule="财报股单票上限减半。" if active else "个股级事件只影响个股。",
        ),
    )


def fixture_reasoning() -> dict:
    return {
        "reasoning_summary": "规则层分数为主，LLM 仅解释风险。",
        "key_drivers": ["ETF proxy 广度改善"],
        "risks": fixture_risks(),
        "evidence": fixture_evidence(),
        "confidence": 0.82,
    }


def fixture_score_card(
    *,
    deterministic_score: float = 67.5,
    score: float = 68.5,
    zone: str = "进攻区",
    slope_state: str = "缓慢改善",
    recommended_exposure: str | None = "60%-80%",
    adjustment: MarketMonitorScoreAdjustment | None = None,
) -> MarketMonitorScoreCard:
    return MarketMonitorScoreCard(
        **fixture_reasoning(),
        deterministic_score=deterministic_score,
        score=score,
        zone=zone,
        delta_1d=2.1,
        delta_5d=8.2,
        slope_state=slope_state,
        recommended_exposure=recommended_exposure,
        factor_breakdown=[fixture_factor()],
        score_adjustment=adjustment,
    )


def fixture_system_risk_card(score: float = 34.6) -> MarketMonitorSystemRiskCard:
    return MarketMonitorSystemRiskCard(
        **fixture_reasoning(),
        deterministic_score=score,
        score=score,
        zone="正常区",
        delta_1d=-1.2,
        delta_5d=-3.5,
        slope_state="风险缓慢回落",
        factor_breakdown=[fixture_factor(polarity="higher_is_riskier", score=35.0)],
        score_adjustment=None,
        liquidity_stress_score=31.2,
        risk_appetite_score=38.0,
        event_triggers=[],
    )


def fixture_style_effectiveness() -> MarketMonitorStyleEffectiveness:
    factor = fixture_factor()
    return MarketMonitorStyleEffectiveness(
        **fixture_reasoning(),
        tactic_layer=MarketMonitorStyleTacticLayer(
            trend_breakout=MarketMonitorLayerMetric(score=52, delta_5d=0.8, valid=False, factor_breakdown=[factor]),
            dip_buy=MarketMonitorLayerMetric(score=66, delta_5d=3.4, valid=True, factor_breakdown=[factor]),
            oversold_bounce=MarketMonitorLayerMetric(score=58, delta_5d=2.1, valid=True, factor_breakdown=[factor]),
            top_tactic="回调低吸",
            avoid_tactic="趋势突破",
        ),
        asset_layer=MarketMonitorStyleAssetLayer(
            large_cap_tech=MarketMonitorLayerMetric(score=61, delta_5d=3.2, preferred=True, factor_breakdown=[factor]),
            small_cap_momentum=MarketMonitorLayerMetric(score=44, delta_5d=-1.2, preferred=False, factor_breakdown=[factor]),
            defensive=MarketMonitorLayerMetric(score=70, delta_5d=2.8, preferred=True, factor_breakdown=[factor]),
            energy_cyclical=MarketMonitorLayerMetric(score=64, delta_5d=1.8, preferred=True, factor_breakdown=[factor]),
            financials=MarketMonitorLayerMetric(score=49, delta_5d=0.4, preferred=False, factor_breakdown=[factor]),
            preferred_assets=["防御板块", "能源/周期"],
            avoid_assets=["小盘高弹性"],
            factor_breakdown=[factor],
        ),
    )


def fixture_execution_card(active_event: bool = True) -> MarketMonitorExecutionCard:
    return MarketMonitorExecutionCard(
        **fixture_reasoning(),
        regime_label="黄绿灯-Swing",
        conflict_mode="长线中性+短线活跃+风险低",
        total_exposure_range="50%-70%",
        new_position_allowed=True,
        chase_breakout_allowed=True,
        dip_buy_allowed=True,
        overnight_allowed=True,
        leverage_allowed=False,
        single_position_cap="12%",
        daily_risk_budget="1.0R",
        tactic_preference="回调低吸 > 趋势突破",
        preferred_assets=["防御板块", "能源/周期"],
        avoid_assets=["小盘高弹性"],
        signal_confirmation=MarketMonitorSignalConfirmation(
            current_regime_observations=1,
            risk_loosening_unlock_in_observations=2,
            note="当前 regime 为新近状态，继续观察 2 个交易日。",
        ),
        event_risk_flag=fixture_event_risk_flag(active_event),
    )


def fixture_panic_card(state: str = "panic_watch", score: float = 41.2) -> MarketMonitorPanicCard:
    return MarketMonitorPanicCard(
        **fixture_reasoning(),
        score=score,
        zone="观察期",
        state=state,
        panic_extreme_score=38.0,
        selling_exhaustion_score=45.0,
        intraday_reversal_score=39.0,
        factor_breakdown=[fixture_factor()],
        action="加入观察列表，等待确认。",
        system_risk_override=None,
        stop_loss="ATR×1.0",
        profit_rule="达 1R 兑现 50%，余仓移止损到成本线。",
        timeout_warning=False,
        refreshes_held=0,
        early_entry_allowed=False,
        max_position_hint="20%-35%",
    )


def fixture_fact_sheet(*, as_of_date: date = date(2026, 4, 11), include_event: bool = True) -> MarketMonitorFactSheet:
    return MarketMonitorFactSheet(
        as_of_date=as_of_date,
        generated_at=fixture_now(),
        local_facts={"symbols": {"SPY": {"latest_close": 523.1}}, "market_proxies": {"SPY": {"close": 523.1}}},
        derived_metrics={"breadth_above_200dma_pct": 63.0, "spy_distance_to_ma200_pct": 4.5},
        event_fact_sheet=[fixture_event_fact()] if include_event else [],
        open_gaps=["缺少交易所级 breadth 原始数据"],
        evidence=fixture_evidence(),
        notes=["已按代理池与降级规则输出结果。"],
    )


def fixture_snapshot(*, as_of_date: date = date(2026, 4, 11), include_event: bool = True) -> MarketMonitorSnapshotResponse:
    event_fact_sheet = [fixture_event_fact()] if include_event else []
    return MarketMonitorSnapshotResponse(
        scorecard_version="2.3.1",
        prompt_version="market-monitor-scorecard-2026-04-v2.3.1",
        model_name="gpt-5.4",
        timestamp=fixture_now(),
        as_of_date=as_of_date,
        data_mode="daily",
        data_freshness="daily_final",
        input_data_status=fixture_input_data_status(),
        missing_data=fixture_missing_data(),
        risks=fixture_risks(),
        event_fact_sheet=event_fact_sheet,
        long_term_score=fixture_score_card(),
        short_term_score=fixture_score_card(deterministic_score=61.3, score=61.3, zone="可做区", recommended_exposure=None),
        system_risk_score=fixture_system_risk_card(),
        style_effectiveness=fixture_style_effectiveness(),
        execution_card=fixture_execution_card(include_event),
        panic_reversal_score=fixture_panic_card(),
        fact_sheet=fixture_fact_sheet(as_of_date=as_of_date, include_event=include_event),
        prompt_traces=[
            MarketMonitorPromptTrace(
                stage="card_judgment",
                card_type="long_term",
                model="gpt-5.4",
                parsed_ok=True,
                input_summary="long_term deterministic facts",
            )
        ],
    )


def fixture_history_point(trade_date: date = date(2026, 4, 10)) -> MarketMonitorHistoryPoint:
    return MarketMonitorHistoryPoint(
        trade_date=trade_date,
        scorecard_version="2.3.1",
        long_term_score=64.0,
        short_term_score=58.0,
        system_risk_score=36.0,
        panic_reversal_score=22.0,
        panic_state="无信号",
        regime_label="黄灯",
    )


def fixture_history_response(*, as_of_date: date = date(2026, 4, 11)) -> MarketMonitorHistoryResponse:
    return MarketMonitorHistoryResponse(as_of_date=as_of_date, points=[fixture_history_point()])


def fixture_data_status(*, as_of_date: date = date(2026, 4, 11), fact_sheet: MarketMonitorFactSheet | None = None) -> MarketMonitorDataStatusResponse:
    return MarketMonitorDataStatusResponse(
        timestamp=fixture_now(),
        as_of_date=as_of_date,
        data_mode="daily",
        data_freshness="daily_final",
        input_data_status=fixture_input_data_status(),
        missing_data=fixture_missing_data(),
        open_gaps=["缺少交易所级 breadth 原始数据"],
        risks=fixture_risks(),
        event_fact_sheet=[],
        fact_sheet=fact_sheet,
    )
