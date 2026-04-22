from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from .data import _expected_market_close_date, build_market_dataset
from .fact_sheet import build_market_fact_sheet
from .inference.cards import MarketMonitorCardInferenceService
from .inference.execution import MarketMonitorExecutionInferenceService
from .indicators import bounded_score, percent_change, rolling_percentile, slope_state, sma, zone_from_score
from .metrics import build_market_snapshot
from .schemas import (
    MarketMonitorActionModifier,
    MarketMonitorDataStatusResponse,
    MarketMonitorDebugCardResponse,
    MarketMonitorEventRiskFlag,
    MarketMonitorExecutionCard,
    MarketMonitorFactSheet,
    MarketMonitorHistoryPoint,
    MarketMonitorHistoryRequest,
    MarketMonitorHistoryResponse,
    MarketMonitorIndexEventRisk,
    MarketMonitorLayerMetric,
    MarketMonitorPanicCard,
    MarketMonitorPromptTrace,
    MarketMonitorRunLlmConfig,
    MarketMonitorRunRequest,
    MarketMonitorScoreCard,
    MarketMonitorSignalConfirmation,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
    MarketMonitorSourceCoverage,
    MarketMonitorStockEventRisk,
    MarketMonitorStyleAssetLayer,
    MarketMonitorStyleEffectiveness,
    MarketMonitorStyleTacticLayer,
    MarketMonitorSystemRiskCard,
)
from .universe import get_market_monitor_universe


def _series(frame: pd.DataFrame, column: str = "Close") -> pd.Series:
    if frame.empty or column not in frame:
        return pd.Series(dtype=float)
    value = frame[column]
    if isinstance(value, pd.DataFrame):
        if value.empty:
            return pd.Series(dtype=float)
        value = value.iloc[:, 0]
    return value.dropna()


class MarketMonitorSnapshotService:
    def __init__(self, llm_config: MarketMonitorRunLlmConfig | None = None) -> None:
        self._universe = get_market_monitor_universe()
        self._inference = MarketMonitorCardInferenceService(llm_config)
        self._execution_inference = MarketMonitorExecutionInferenceService(llm_config)

    def get_snapshot(self, request: MarketMonitorSnapshotRequest) -> MarketMonitorSnapshotResponse:
        as_of_date = request.as_of_date or date.today()
        dataset = build_market_dataset(self._universe, as_of_date, force_refresh=request.force_refresh)
        return self._build_snapshot(as_of_date, dataset)

    def get_history(self, request: MarketMonitorHistoryRequest) -> MarketMonitorHistoryResponse:
        as_of_date = request.as_of_date or date.today()
        snapshots = self.get_history_snapshots(request)
        return self.build_history_response(as_of_date, snapshots)

    def resolve_history_trade_dates(self, request: MarketMonitorHistoryRequest) -> list[date]:
        as_of_date = request.as_of_date or date.today()
        trade_dates: list[date] = []
        cursor = as_of_date
        attempts = 0
        while len(trade_dates) < request.days and attempts < request.days * 3:
            attempts += 1
            if _expected_market_close_date(cursor).date() != cursor:
                cursor -= timedelta(days=1)
                continue
            trade_dates.append(cursor)
            cursor -= timedelta(days=1)
        trade_dates.sort()
        return trade_dates

    def get_history_snapshots(
        self,
        request: MarketMonitorHistoryRequest,
        trade_dates: list[date] | None = None,
    ) -> list[MarketMonitorSnapshotResponse]:
        dates_to_build = trade_dates or self.resolve_history_trade_dates(request)
        snapshots: list[MarketMonitorSnapshotResponse] = []
        for trade_date in dates_to_build:
            dataset = build_market_dataset(self._universe, trade_date, force_refresh=request.force_refresh)
            snapshots.append(self._build_snapshot(trade_date, dataset))
        snapshots.sort(key=lambda item: item.as_of_date)
        return snapshots

    def build_history_response(
        self,
        as_of_date: date,
        snapshots: list[MarketMonitorSnapshotResponse],
    ) -> MarketMonitorHistoryResponse:
        return MarketMonitorHistoryResponse(
            as_of_date=as_of_date,
            points=[
                MarketMonitorHistoryPoint(
                    trade_date=snapshot.as_of_date,
                    long_term_score=snapshot.long_term_score.score,
                    short_term_score=snapshot.short_term_score.score,
                    system_risk_score=snapshot.system_risk_score.score,
                    panic_score=snapshot.panic_reversal_score.score,
                    regime_label=snapshot.execution_card.regime_label,
                )
                for snapshot in snapshots
            ],
        )

    def get_data_status(self, request: MarketMonitorSnapshotRequest) -> MarketMonitorDataStatusResponse:
        as_of_date = request.as_of_date or date.today()
        dataset = build_market_dataset(self._universe, as_of_date, force_refresh=request.force_refresh)
        snapshot = self._build_snapshot(as_of_date, dataset)
        gaps = self._build_open_gaps(dataset["core"])
        return MarketMonitorDataStatusResponse(
            timestamp=snapshot.timestamp,
            as_of_date=snapshot.as_of_date,
            source_coverage=snapshot.source_coverage,
            degraded_factors=snapshot.degraded_factors,
            notes=snapshot.notes,
            open_gaps=gaps,
            fact_sheet=snapshot.fact_sheet,
        )

    def get_debug_card(
        self,
        request: MarketMonitorRunRequest,
        fact_sheet: MarketMonitorFactSheet | None,
        fact_sheet_source_run_id: str | None,
    ) -> MarketMonitorDebugCardResponse:
        debug_options = request.debug_options
        if debug_options is None or debug_options.debug_card is None:
            raise ValueError("debug_card 运行缺少 debug_options.debug_card")
        as_of_date = request.as_of_date or date.today()
        dataset = build_market_dataset(self._universe, as_of_date, force_refresh=request.force_refresh)
        core_data = dataset["core"]
        cache_summary = dataset.get("cache_summary", {})
        local_market_data, derived_metrics = build_market_snapshot(core_data, self._universe["breadth_proxy_symbols"])
        source_coverage, _, notes = self._build_data_quality(cache_summary, core_data)
        open_gaps = self._build_open_gaps(core_data)
        current_fact_sheet = fact_sheet or build_market_fact_sheet(
            as_of_date=as_of_date,
            generated_at=datetime.now(timezone.utc),
            core_data=core_data,
            local_market_data=local_market_data,
            derived_metrics=derived_metrics,
            source_coverage=source_coverage,
            open_gaps=open_gaps,
            notes=notes,
        )
        long_term_fallback = lambda: self._build_long_term_card(core_data, derived_metrics)
        short_term_fallback = lambda: self._build_short_term_card(core_data)
        system_risk_fallback = lambda: self._build_system_risk_card(core_data, derived_metrics)
        style_fallback = lambda: self._build_style_effectiveness(core_data)
        event_risk_fallback = lambda: self._build_event_risk(as_of_date)
        card_type = debug_options.debug_card
        if card_type == "long_term":
            result = self._inference.infer_long_term(current_fact_sheet, long_term_fallback)
        elif card_type == "short_term":
            result = self._inference.infer_short_term(current_fact_sheet, short_term_fallback)
        elif card_type == "system_risk":
            result = self._inference.infer_system_risk(current_fact_sheet, system_risk_fallback)
        elif card_type == "style":
            result = self._inference.infer_style(current_fact_sheet, style_fallback)
        elif card_type == "event_risk":
            result = self._inference.infer_event_risk(current_fact_sheet, event_risk_fallback)
        elif card_type == "panic":
            system_risk = system_risk_fallback()
            result = self._inference.infer_panic(
                current_fact_sheet,
                lambda: self._build_panic_card(core_data, system_risk.score),
            )
        else:
            long_term = long_term_fallback()
            short_term = short_term_fallback()
            system_risk = system_risk_fallback()
            style = style_fallback()
            event_risk = event_risk_fallback()
            result = self._execution_inference.infer_execution(
                fact_sheet=current_fact_sheet,
                long_term=long_term,
                short_term=short_term,
                system_risk=system_risk,
                style=style,
                event_risk=event_risk,
                fallback=lambda: self._build_execution_card(long_term, short_term, system_risk, style, event_risk),
            )
        return MarketMonitorDebugCardResponse(
            card_type=card_type,
            as_of_date=as_of_date,
            fact_sheet_reused=fact_sheet is not None,
            fact_sheet_source_run_id=fact_sheet_source_run_id,
            result=result.payload.model_dump(mode="json"),
            prompt_traces=[result.trace],
        )

    def _build_snapshot(self, as_of_date: date, dataset: dict[str, Any]) -> MarketMonitorSnapshotResponse:
        core_data = dataset["core"]
        cache_summary = dataset.get("cache_summary", {})
        local_market_data, derived_metrics = build_market_snapshot(core_data, self._universe["breadth_proxy_symbols"])
        source_coverage, degraded_factors, notes = self._build_data_quality(cache_summary, core_data)
        open_gaps = self._build_open_gaps(core_data)
        expected_close = _expected_market_close_date(as_of_date)
        timestamp = datetime.now(timezone.utc)
        data_freshness = "delayed_15min" if expected_close.date() == as_of_date else "previous_trading_day"
        fact_sheet = build_market_fact_sheet(
            as_of_date=as_of_date,
            generated_at=timestamp,
            core_data=core_data,
            local_market_data=local_market_data,
            derived_metrics=derived_metrics,
            source_coverage=source_coverage,
            open_gaps=open_gaps,
            notes=notes,
        )
        long_term_fallback = lambda: self._build_long_term_card(core_data, derived_metrics)
        short_term_fallback = lambda: self._build_short_term_card(core_data)
        system_risk_fallback = lambda: self._build_system_risk_card(core_data, derived_metrics)
        style_fallback = lambda: self._build_style_effectiveness(core_data)
        event_risk_fallback = lambda: self._build_event_risk(as_of_date)
        long_term_result = self._inference.infer_long_term(fact_sheet, long_term_fallback)
        short_term_result = self._inference.infer_short_term(fact_sheet, short_term_fallback)
        system_risk_result = self._inference.infer_system_risk(fact_sheet, system_risk_fallback)
        style_result = self._inference.infer_style(fact_sheet, style_fallback)
        event_risk_result = self._inference.infer_event_risk(fact_sheet, event_risk_fallback)
        long_term = long_term_result.payload
        short_term = short_term_result.payload
        system_risk = system_risk_result.payload
        style = style_result.payload
        event_risk = event_risk_result.payload
        execution_fallback = lambda: self._build_execution_card(long_term, short_term, system_risk, style, event_risk)
        execution_result = self._execution_inference.infer_execution(
            fact_sheet=fact_sheet,
            long_term=long_term,
            short_term=short_term,
            system_risk=system_risk,
            style=style,
            event_risk=event_risk,
            fallback=execution_fallback,
        )
        execution = execution_result.payload
        panic_fallback = lambda: self._build_panic_card(core_data, system_risk.score)
        panic_result = self._inference.infer_panic(fact_sheet, panic_fallback)
        panic = panic_result.payload
        prompt_traces = [
            long_term_result.trace,
            short_term_result.trace,
            system_risk_result.trace,
            style_result.trace,
            event_risk_result.trace,
            panic_result.trace,
            execution_result.trace,
        ]
        return MarketMonitorSnapshotResponse(
            timestamp=timestamp,
            as_of_date=as_of_date,
            data_freshness=data_freshness,
            long_term_score=long_term,
            short_term_score=short_term,
            system_risk_score=system_risk,
            style_effectiveness=style,
            execution_card=execution,
            panic_reversal_score=panic,
            event_risk_flag=event_risk,
            source_coverage=source_coverage,
            degraded_factors=degraded_factors,
            notes=notes,
            fact_sheet=fact_sheet,
            prompt_traces=prompt_traces,
        )

    def _build_long_term_card(self, core_data: dict[str, pd.DataFrame], derived_metrics: dict[str, Any]) -> MarketMonitorScoreCard:
        spy = _series(core_data.get("SPY", pd.DataFrame()))
        qqq = _series(core_data.get("QQQ", pd.DataFrame()))
        iwm = _series(core_data.get("IWM", pd.DataFrame()))
        dia = _series(core_data.get("DIA", pd.DataFrame()))
        xlu = _series(core_data.get("XLU", pd.DataFrame()))
        xlp = _series(core_data.get("XLP", pd.DataFrame()))
        xlv = _series(core_data.get("XLV", pd.DataFrame()))
        breadth = float(derived_metrics.get("breadth_above_200dma_pct", 0.0))
        distance = float(derived_metrics.get("spy_distance_to_ma200_pct", 0.0))
        range_pos = float(derived_metrics.get("spy_range_position_3m_pct", 50.0))
        qqq_momentum = percent_change(qqq, 20)
        iwm_momentum = percent_change(iwm, 20)
        dia_momentum = percent_change(dia, 20)
        offense = (percent_change(qqq, 10) + percent_change(iwm, 10)) / 2
        defense = (percent_change(xlu, 10) + percent_change(xlp, 10) + percent_change(xlv, 10)) / 3
        offense_spread = offense - defense
        score = bounded_score(
            42
            + distance * 3.2
            + breadth * 0.22
            + range_pos * 0.18
            + qqq_momentum * 1.0
            + iwm_momentum * 0.8
            + dia_momentum * 0.5
            + offense_spread * 2.5
        )
        delta_1d = self._rolling_score_delta(spy, 1)
        delta_5d = self._rolling_score_delta(spy, 5)
        zone = zone_from_score(score, [(35, "防守区"), (50, "谨慎区"), (65, "试仓区"), (80, "进攻区"), (101, "强趋势区")])
        recommended_exposure = self._exposure_for_long_term(score)
        summary = f"SPY 距 200 日线 {distance:.1f}%，ETF proxy 广度 {breadth:.0f}%，进攻/防御价差 {offense_spread:.1f}，长线环境处于{zone}。"
        action = f"建议总仓位以 {recommended_exposure} 为主，优先持有顺趋势方向。"
        return MarketMonitorScoreCard(
            score=round(score, 1),
            zone=zone,
            delta_1d=round(delta_1d, 1),
            delta_5d=round(delta_5d, 1),
            slope_state=slope_state(delta_1d, delta_5d),
            summary=summary,
            action=action,
            recommended_exposure=recommended_exposure,
        )

    def _build_short_term_card(self, core_data: dict[str, pd.DataFrame]) -> MarketMonitorScoreCard:
        sector_scores = []
        for symbol in self._universe["sector_etfs"]:
            series = _series(core_data.get(symbol, pd.DataFrame()))
            sector_scores.append(percent_change(series, 5) - percent_change(series, 20) * 0.35)
        spy = _series(core_data.get("SPY", pd.DataFrame()))
        avg_sector = sum(sector_scores) / len(sector_scores) if sector_scores else 0.0
        atr_proxy = abs(percent_change(spy, 5))
        score = bounded_score(50 + avg_sector * 4 - max(0.0, atr_proxy - 2.5) * 6)
        delta_1d = self._rolling_score_delta(spy, 1, multiplier=1.6)
        delta_5d = self._rolling_score_delta(spy, 5, multiplier=2.4)
        zone = zone_from_score(score, [(20, "极差区"), (35, "弱势区"), (50, "观察区"), (65, "可做区"), (80, "活跃区"), (101, "高胜率区")])
        summary = f"行业 ETF 动量扩散均值 {avg_sector:.1f}，短线环境处于{zone}。"
        action = self._short_term_action(score)
        return MarketMonitorScoreCard(
            score=round(score, 1),
            zone=zone,
            delta_1d=round(delta_1d, 1),
            delta_5d=round(delta_5d, 1),
            slope_state=slope_state(delta_1d, delta_5d),
            summary=summary,
            action=action,
        )

    def _build_system_risk_card(self, core_data: dict[str, pd.DataFrame], derived_metrics: dict[str, Any]) -> MarketMonitorSystemRiskCard:
        spy = _series(core_data.get("SPY", pd.DataFrame()))
        iwm = _series(core_data.get("IWM", pd.DataFrame()))
        arkk = _series(core_data.get("ARKK", pd.DataFrame()))
        xlu = _series(core_data.get("XLU", pd.DataFrame()))
        lqd = _series(core_data.get("LQD", pd.DataFrame()))
        jnk = _series(core_data.get("JNK", pd.DataFrame()))
        vix = _series(core_data.get("^VIX", pd.DataFrame()))
        breadth = float(derived_metrics.get("breadth_above_200dma_pct", 0.0))
        iwm_rel = percent_change(iwm, 5) - percent_change(spy, 5)
        arkk_rel = percent_change(arkk, 5) - percent_change(spy, 5)
        defensive_rel = percent_change(xlu, 5) - percent_change(spy, 5)
        lqd_rel = percent_change(lqd, 5) - percent_change(spy, 5)
        jnk_rel = percent_change(jnk, 5) - percent_change(spy, 5)
        credit_spread_proxy = lqd_rel - jnk_rel
        vix_close = float(vix.iloc[-1]) if not vix.empty else 20.0
        vix_percentile = rolling_percentile(vix, vix_close) if not vix.empty else 50.0
        liquidity = bounded_score(vix_percentile * 0.6 + max(0.0, credit_spread_proxy) * 18 + max(0.0, 58 - breadth) * 0.45)
        appetite = bounded_score(
            52
            - iwm_rel * 8
            - arkk_rel * 6
            + max(0.0, defensive_rel) * 10
            + max(0.0, -jnk_rel) * 12
            + max(0.0, 55 - breadth) * 0.35
        )
        score = bounded_score(liquidity * 0.55 + appetite * 0.45)
        delta_1d = self._rolling_score_delta(vix, 1, multiplier=2.2)
        delta_5d = self._rolling_score_delta(vix, 5, multiplier=3.1)
        zone = zone_from_score(score, [(20, "低压区"), (45, "正常区"), (60, "压力区"), (80, "高压区"), (101, "危机区")])
        summary = f"VIX 水位 {vix_close:.1f}，信用代理价差 {credit_spread_proxy:.1f}，高 beta 偏好 {((iwm_rel + arkk_rel) / 2):.1f}，系统风险处于{zone}。"
        action = self._system_risk_action(score)
        return MarketMonitorSystemRiskCard(
            score=round(score, 1),
            zone=zone,
            delta_1d=round(delta_1d, 1),
            delta_5d=round(delta_5d, 1),
            slope_state=slope_state(delta_1d, delta_5d),
            summary=summary,
            action=action,
            liquidity_stress_score=round(liquidity, 1),
            risk_appetite_score=round(appetite, 1),
        )

    def _build_style_effectiveness(self, core_data: dict[str, pd.DataFrame]) -> MarketMonitorStyleEffectiveness:
        def metric(series: pd.Series, multiplier: float = 3.5) -> tuple[float, float]:
            delta_5d = percent_change(series, 5)
            score = bounded_score(50 + delta_5d * multiplier)
            return round(score, 1), round(delta_5d, 1)

        spy = _series(core_data.get("SPY", pd.DataFrame()))
        qqq = _series(core_data.get("QQQ", pd.DataFrame()))
        iwm = _series(core_data.get("IWM", pd.DataFrame()))
        xlu = _series(core_data.get("XLU", pd.DataFrame()))
        xlv = _series(core_data.get("XLV", pd.DataFrame()))
        xlp = _series(core_data.get("XLP", pd.DataFrame()))
        xle = _series(core_data.get("XLE", pd.DataFrame()))
        xlb = _series(core_data.get("XLB", pd.DataFrame()))
        xlf = _series(core_data.get("XLF", pd.DataFrame()))

        trend_breakout_score, trend_breakout_delta = metric(qqq)
        dip_buy_score, dip_buy_delta = metric(spy, 2.8)
        oversold_score, oversold_delta = metric(iwm, 4.0)
        large_cap_tech_score, large_cap_tech_delta = metric(qqq)
        small_cap_score, small_cap_delta = metric(iwm)
        defensive_series = pd.concat([xlu, xlv, xlp], axis=1).mean(axis=1).dropna()
        defensive_score, defensive_delta = metric(defensive_series, 3.2)
        energy_series = pd.concat([xle, xlb], axis=1).mean(axis=1).dropna()
        energy_score, energy_delta = metric(energy_series, 3.2)
        financials_score, financials_delta = metric(xlf, 3.0)

        tactic_pairs = {
            "趋势突破": trend_breakout_score,
            "回调低吸": dip_buy_score,
            "超跌反弹": oversold_score,
        }
        top_tactic = max(tactic_pairs, key=tactic_pairs.get)
        avoid_tactic = min(tactic_pairs, key=tactic_pairs.get)

        asset_pairs = {
            "大盘科技": large_cap_tech_score,
            "小盘高弹性": small_cap_score,
            "防御板块": defensive_score,
            "能源/周期": energy_score,
            "金融": financials_score,
        }
        preferred_assets = [name for name, score in asset_pairs.items() if score >= 60]
        avoid_assets = [name for name, score in asset_pairs.items() if score < 45]

        return MarketMonitorStyleEffectiveness(
            tactic_layer=MarketMonitorStyleTacticLayer(
                trend_breakout=MarketMonitorLayerMetric(score=trend_breakout_score, delta_5d=trend_breakout_delta, valid=trend_breakout_score >= 55),
                dip_buy=MarketMonitorLayerMetric(score=dip_buy_score, delta_5d=dip_buy_delta, valid=dip_buy_score >= 55),
                oversold_bounce=MarketMonitorLayerMetric(score=oversold_score, delta_5d=oversold_delta, valid=oversold_score >= 55),
                top_tactic=top_tactic,
                avoid_tactic=avoid_tactic,
            ),
            asset_layer=MarketMonitorStyleAssetLayer(
                large_cap_tech=MarketMonitorLayerMetric(score=large_cap_tech_score, delta_5d=large_cap_tech_delta, preferred=large_cap_tech_score >= 60),
                small_cap_momentum=MarketMonitorLayerMetric(score=small_cap_score, delta_5d=small_cap_delta, preferred=small_cap_score >= 60),
                defensive=MarketMonitorLayerMetric(score=defensive_score, delta_5d=defensive_delta, preferred=defensive_score >= 60),
                energy_cyclical=MarketMonitorLayerMetric(score=energy_score, delta_5d=energy_delta, preferred=energy_score >= 60),
                financials=MarketMonitorLayerMetric(score=financials_score, delta_5d=financials_delta, preferred=financials_score >= 60),
                preferred_assets=preferred_assets,
                avoid_assets=avoid_assets,
            ),
        )

    def _build_event_risk(self, as_of_date: date) -> MarketMonitorEventRiskFlag:
        index_level = MarketMonitorIndexEventRisk(active=False)
        if as_of_date.weekday() in {1, 2, 3}:
            index_level = MarketMonitorIndexEventRisk(
                active=True,
                type="搜索增强缺失-默认收紧",
                days_to_event=None,
                action_modifier=MarketMonitorActionModifier(
                    new_position_allowed=None,
                    overnight_allowed=False,
                    single_position_cap_multiplier=0.8,
                    note="当前未注入搜索事件事实，指数级事件风险仅按默认收紧规则处理，不放宽风险边界。",
                ),
            )
        stock_level = MarketMonitorStockEventRisk(
            earnings_stocks=[],
            rule="未接入搜索财报日历时，不预填个股名单；若后续搜索命中财报股，仅对该股减半仓位并禁追高。",
        )
        return MarketMonitorEventRiskFlag(
            index_level=index_level,
            stock_level=stock_level,
            reasoning_summary="当前运行未注入搜索增强事件事实，事件风险卡采用保守降级输出。",
            key_drivers=[
                "指数级事件只允许收紧执行权限",
                "个股级事件不应污染指数 regime",
            ],
            risks=["缺少宏观日历与财报搜索结果时，事件风险只能保守降级，无法给出精确事件窗口。"],
            confidence="low",
        )

    def _build_execution_card(
        self,
        long_term: MarketMonitorScoreCard,
        short_term: MarketMonitorScoreCard,
        system_risk: MarketMonitorSystemRiskCard,
        style: MarketMonitorStyleEffectiveness,
        event_risk: MarketMonitorEventRiskFlag,
    ) -> MarketMonitorExecutionCard:
        if system_risk.score > 70:
            regime_label = "红灯"
            conflict_mode = "系统风险高压-危机模式"
            total_exposure_range = "0%-20%"
            new_position_allowed = False
            chase_breakout_allowed = False
            dip_buy_allowed = False
            overnight_allowed = False
            leverage_allowed = False
            single_position_cap = "5%"
            daily_risk_budget = "0.25R"
        elif long_term.score >= 65 and short_term.score >= 55 and system_risk.score <= 35:
            regime_label = "绿灯"
            conflict_mode = "长强短强-顺势进攻"
            total_exposure_range = "70%-90%"
            new_position_allowed = True
            chase_breakout_allowed = True
            dip_buy_allowed = True
            overnight_allowed = True
            leverage_allowed = False
            single_position_cap = "12%"
            daily_risk_budget = "1.0R"
        elif 45 <= long_term.score < 65 and short_term.score >= 60 and system_risk.score <= 35:
            regime_label = "黄绿灯-Swing"
            conflict_mode = "长线中性+短线活跃+风险低"
            total_exposure_range = "50%-70%"
            new_position_allowed = True
            chase_breakout_allowed = True
            dip_buy_allowed = True
            overnight_allowed = True
            leverage_allowed = False
            single_position_cap = "12%"
            daily_risk_budget = "1.0R"
        elif long_term.score >= 65 and short_term.score < 25:
            regime_label = "橙灯"
            conflict_mode = "长强极弱-等待恐慌修复"
            total_exposure_range = "20%-35%"
            new_position_allowed = False
            chase_breakout_allowed = False
            dip_buy_allowed = False
            overnight_allowed = False
            leverage_allowed = False
            single_position_cap = "8%"
            daily_risk_budget = "0.5R"
        elif long_term.score >= 65 and short_term.score < 45:
            regime_label = "黄灯-等待"
            conflict_mode = "长强短弱-等待修复"
            total_exposure_range = "35%-50%"
            new_position_allowed = True
            chase_breakout_allowed = False
            dip_buy_allowed = True
            overnight_allowed = False
            leverage_allowed = False
            single_position_cap = "10%"
            daily_risk_budget = "0.6R"
        elif long_term.score < 45 and short_term.score >= 55 and system_risk.score <= 35:
            regime_label = "黄灯-短线"
            conflict_mode = "长弱短强-仅短线博弈"
            total_exposure_range = "20%-35%"
            new_position_allowed = True
            chase_breakout_allowed = True
            dip_buy_allowed = True
            overnight_allowed = False
            leverage_allowed = False
            single_position_cap = "6%"
            daily_risk_budget = "0.5R"
        elif short_term.score < 45 or long_term.score < 45:
            regime_label = "橙灯"
            conflict_mode = "中性转弱-控仓防守"
            total_exposure_range = "20%-40%"
            new_position_allowed = False
            chase_breakout_allowed = False
            dip_buy_allowed = True
            overnight_allowed = False
            leverage_allowed = False
            single_position_cap = "8%"
            daily_risk_budget = "0.5R"
        else:
            regime_label = "黄灯"
            conflict_mode = "中性环境-低频参与"
            total_exposure_range = "40%-60%"
            new_position_allowed = True
            chase_breakout_allowed = False
            dip_buy_allowed = True
            overnight_allowed = True
            leverage_allowed = False
            single_position_cap = "10%"
            daily_risk_budget = "0.75R"

        if event_risk.index_level.active and event_risk.index_level.action_modifier:
            modifier = event_risk.index_level.action_modifier
            if modifier.new_position_allowed is False:
                new_position_allowed = False
            if modifier.overnight_allowed is False:
                overnight_allowed = False
            if modifier.single_position_cap_multiplier == 0.8:
                cap_mapping = {
                    "12%": "10%",
                    "10%": "8%",
                    "8%": "6%",
                    "6%": "5%",
                }
                single_position_cap = cap_mapping.get(single_position_cap, single_position_cap)

        preferred_assets = style.asset_layer.preferred_assets or ["防御板块"]
        avoid_assets = style.asset_layer.avoid_assets
        summary = f"当前处于{regime_label}，总仓建议 {total_exposure_range}，优先 {style.tactic_layer.top_tactic}。"
        return MarketMonitorExecutionCard(
            regime_label=regime_label,
            conflict_mode=conflict_mode,
            total_exposure_range=total_exposure_range,
            new_position_allowed=new_position_allowed,
            chase_breakout_allowed=chase_breakout_allowed,
            dip_buy_allowed=dip_buy_allowed,
            overnight_allowed=overnight_allowed,
            leverage_allowed=leverage_allowed,
            single_position_cap=single_position_cap,
            daily_risk_budget=daily_risk_budget,
            tactic_preference=f"{style.tactic_layer.top_tactic} > {style.tactic_layer.avoid_tactic}",
            preferred_assets=preferred_assets,
            avoid_assets=avoid_assets,
            signal_confirmation=MarketMonitorSignalConfirmation(
                current_regime_observations=1,
                risk_loosening_unlock_in_observations=2,
                note="当前 regime 为新近状态；若要放宽风险边界，需再连续观察 2 次刷新保持。",
            ),
            event_risk_flag=event_risk,
            summary=summary,
        )

    def _build_panic_card(self, core_data: dict[str, pd.DataFrame], system_risk_score: float) -> MarketMonitorPanicCard:
        spy = _series(core_data.get("SPY", pd.DataFrame()))
        qqq = _series(core_data.get("QQQ", pd.DataFrame()))
        iwm = _series(core_data.get("IWM", pd.DataFrame()))
        dia = _series(core_data.get("DIA", pd.DataFrame()))
        arkk = _series(core_data.get("ARKK", pd.DataFrame()))
        xle = _series(core_data.get("XLE", pd.DataFrame()))
        xlf = _series(core_data.get("XLF", pd.DataFrame()))
        vix = _series(core_data.get("^VIX", pd.DataFrame()))

        proxy_drops = [
            abs(min(0.0, percent_change(series, 1)))
            for series in [spy, qqq, iwm, dia]
        ]
        panic_drop = max(proxy_drops) if proxy_drops else 0.0
        vix_jump = max(0.0, percent_change(vix, 1)) if not vix.empty else 0.0
        high_beta_slump = abs(min(0.0, (percent_change(arkk, 1) + percent_change(iwm, 1)) / 2))
        panic_extreme = bounded_score(panic_drop * 22 + vix_jump * 1.4 + high_beta_slump * 8)

        leaders = [iwm, arkk, xle, xlf]
        leader_relief_count = sum(1 for series in leaders if percent_change(series, 1) > -1.0)
        selling_exhaustion = bounded_score(30 + leader_relief_count * 16 + max(0.0, percent_change(spy, 1) + 2.0) * 10)

        intraday_reversal = bounded_score(
            25
            + max(0.0, percent_change(spy, 1)) * 12
            + max(0.0, percent_change(qqq, 1)) * 8
            + max(0.0, percent_change(arkk, 1)) * 6
        )
        score = bounded_score(panic_extreme * 0.45 + selling_exhaustion * 0.3 + intraday_reversal * 0.25)
        if panic_extreme >= 80:
            state = "panic_confirmed"
            zone = "强反转窗口"
        elif panic_extreme >= 35 and score >= 50:
            state = "panic_confirmed"
            zone = "一级试错"
        elif panic_extreme >= 35:
            state = "panic_watch"
            zone = "观察期"
        else:
            state = "无信号"
            zone = "无信号"
        early_entry_allowed = state == "panic_confirmed" and intraday_reversal >= 60
        max_position_hint = "15%" if system_risk_score > 80 else "20%-35%"
        action = {
            "无信号": "不启动恐慌策略。",
            "panic_watch": "加入观察列表，等待确认。",
            "panic_confirmed": "允许轻仓试错，但采用更紧止损。",
        }[state]
        return MarketMonitorPanicCard(
            score=round(score, 1),
            zone=zone,
            state=state,
            panic_extreme_score=round(panic_extreme, 1),
            selling_exhaustion_score=round(selling_exhaustion, 1),
            intraday_reversal_score=round(intraday_reversal, 1),
            action=action,
            system_risk_override="系统风险>80 时，反弹仓上限强制≤15%" if system_risk_score > 80 else None,
            stop_loss="ATR×1.0",
            profit_rule="达 1R 兑现 50%，余仓移止损到成本线。",
            timeout_warning=False,
            refreshes_held=0,
            early_entry_allowed=early_entry_allowed,
            max_position_hint=max_position_hint,
        )

    def _build_data_quality(
        self,
        cache_summary: dict[str, Any],
        core_data: dict[str, pd.DataFrame],
    ) -> tuple[MarketMonitorSourceCoverage, list[str], list[str]]:
        counts = cache_summary.get("counts", {})
        missing_sources = []
        degraded_factors = []
        notes = []
        if counts.get("cache_missing", 0) or counts.get("cache_corrupted", 0) or counts.get("cache_invalid_structure", 0):
            degraded_factors.append("部分 ETF/指数日线存在缓存缺口")
        if counts.get("cache_stale", 0):
            degraded_factors.append("部分标的使用 stale fallback")
        open_gaps = self._build_open_gaps(core_data)
        for gap in open_gaps:
            if "VIX 期限结构" in gap:
                missing_sources.append("VIX 期限结构")
                degraded_factors.append("系统风险高级波动结构未接入")
            elif "breadth" in gap:
                missing_sources.append("交易所级 breadth")
                degraded_factors.append("广度因子使用 ETF 代理池近似")
            elif "宏观与财报事件" in gap:
                missing_sources.append("未来三日事件日历")
                degraded_factors.append("事件风险仍为简化版")
            elif "RS 龙头" in gap:
                missing_sources.append("股票级 RS 横截面")
                degraded_factors.append("风格/龙头因子使用 ETF 代理")
        degraded_factors = list(dict.fromkeys(degraded_factors))
        missing_sources = list(dict.fromkeys(missing_sources))
        notes.extend(open_gaps)
        completeness = "high"
        if degraded_factors:
            completeness = "medium"
        if len(degraded_factors) >= 4:
            completeness = "low"
        available_sources = ["ETF/指数日线", "VIX 日线", "本地缓存"]
        if not missing_sources:
            notes.append("当前数据完整度较高。")
        else:
            notes.append("已按代理池与降级规则输出结果。")
        return (
            MarketMonitorSourceCoverage(
                completeness=completeness,
                available_sources=available_sources,
                missing_sources=missing_sources,
                degraded=bool(degraded_factors),
            ),
            degraded_factors,
            notes,
        )

    def _build_open_gaps(self, core_data: dict[str, Any]) -> list[str]:
        gaps: list[str] = []
        for symbol in ["SPY", "QQQ", "IWM", "^VIX"]:
            frame = core_data.get(symbol)
            if frame is None or frame.empty:
                gaps.append(f"缺少 {symbol} 日线")
        gaps.extend(
            [
                "缺少 VIX 期限结构",
                "缺少交易所级 breadth 原始数据",
                "缺少未来三日宏观与财报事件原始日历",
                "缺少股票级 RS 龙头横截面",
            ]
        )
        return gaps

    def _rolling_score_delta(self, series: pd.Series, periods: int, multiplier: float = 1.0) -> float:
        value = percent_change(series, periods)
        return value * multiplier

    def _exposure_for_long_term(self, score: float) -> str:
        if score < 35:
            return "0%-20%"
        if score < 50:
            return "20%-40%"
        if score < 65:
            return "40%-60%"
        if score < 80:
            return "60%-80%"
        return "80%-100%"

    def _short_term_action(self, score: float) -> str:
        if score < 20:
            return "禁止追涨，只等逆向机会。"
        if score < 35:
            return "轻仓试错，不隔夜高波动标的。"
        if score < 50:
            return "可观察，不主动进攻。"
        if score < 65:
            return "允许低吸、突破、事件交易。"
        if score < 80:
            return "允许提高交易频率，但保持风控。"
        return "短线积极进攻，仍需风控。"

    def _system_risk_action(self, score: float) -> str:
        if score < 20:
            return "允许正常进攻。"
        if score < 45:
            return "维持常规风控。"
        if score < 60:
            return "缩仓、防追高、降低单票风险。"
        if score < 80:
            return "禁止杠杆，优先保护净值。"
        return "进入危机模式，只保留极低风险仓位。"
