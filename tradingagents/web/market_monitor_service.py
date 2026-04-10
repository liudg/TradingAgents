from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from typing import Any

import pandas as pd

from tradingagents.web.market_monitor_data import build_market_dataset
from tradingagents.web.market_monitor_llm import MarketMonitorLLMService
from tradingagents.web.market_monitor_schemas import (
    MarketEventRiskFlag,
    MarketExecutionCard,
    MarketExecutionSignalConfirmation,
    MarketHistoryPoint,
    MarketIndexEventRisk,
    MarketMonitorDataStatusResponse,
    MarketMonitorHistoryResponse,
    MarketMonitorModelOverlay,
    MarketMonitorRuleSnapshot,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
    MarketPanicReversalCard,
    MarketScoreCard,
    MarketSourceCoverage,
    MarketStockEventRisk,
    MarketStyleAssetLayer,
    MarketStyleEffectiveness,
    MarketStyleSignal,
    MarketStyleTacticLayer,
)
from tradingagents.web.market_monitor_scoring import (
    LONG_TERM_ZONES,
    SHORT_TERM_ZONES,
    SYSTEM_RISK_ZONES,
    build_breadth_ratio,
    build_long_term_series,
    build_short_term_series,
    build_system_risk_series,
    score_asset_layer,
    score_tactic_layer,
    summarize_score,
)
from tradingagents.web.market_monitor_universe import get_market_monitor_universe


class MarketMonitorService:
    """Market monitor service using live yfinance data and optional model overlay."""

    def __init__(self) -> None:
        self._overlay_service = MarketMonitorLLMService()

    def get_snapshot(self, request: MarketMonitorSnapshotRequest) -> MarketMonitorSnapshotResponse:
        as_of_date = request.as_of_date or date.today()
        universe = get_market_monitor_universe()
        dataset = build_market_dataset(universe, as_of_date)
        rule_snapshot = self._build_rule_snapshot(dataset, universe)
        context_queries = self._build_context_queries(rule_snapshot)
        model_overlay = self._overlay_service.create_overlay(rule_snapshot, as_of_date.isoformat(), context_queries)
        final_execution_card = self._merge_overlay(rule_snapshot, model_overlay)

        return MarketMonitorSnapshotResponse(
            timestamp=datetime.now(),
            as_of_date=as_of_date,
            rule_snapshot=rule_snapshot,
            model_overlay=model_overlay,
            final_execution_card=final_execution_card,
        )

    def get_history(self, as_of_date: date, days: int = 10) -> MarketMonitorHistoryResponse:
        universe = get_market_monitor_universe()
        dataset = build_market_dataset(universe, as_of_date)
        core_data = dataset["core"]
        missing_required = self._missing_required_symbols(core_data)
        if missing_required:
            return MarketMonitorHistoryResponse(as_of_date=as_of_date, points=[])

        breadth_ratio = build_breadth_ratio(dataset["nasdaq_100"])
        sector_data = {symbol: core_data[symbol] for symbol in universe["sector_etfs"] if symbol in core_data}

        long_term_series = build_long_term_series(core_data, breadth_ratio).dropna().tail(days)
        short_term_series = (
            build_short_term_series(core_data, sector_data, breadth_ratio)
            .dropna()
            .reindex(long_term_series.index)
            .ffill()
        )
        system_risk_series = (
            build_system_risk_series(core_data, breadth_ratio)
            .dropna()
            .reindex(long_term_series.index)
            .ffill()
        )

        points: list[MarketHistoryPoint] = []
        for dt in long_term_series.index:
            long_score = float(long_term_series.loc[dt])
            short_score = float(short_term_series.loc[dt]) if dt in short_term_series.index else 50.0
            risk_score = float(system_risk_series.loc[dt]) if dt in system_risk_series.index else 50.0
            points.append(
                MarketHistoryPoint(
                    trade_date=dt.date(),
                    regime_label=self._regime_label(long_score, short_score, risk_score),
                    long_term_score=long_score,
                    short_term_score=short_score,
                    system_risk_score=risk_score,
                    panic_reversal_score=max(0.0, min(100.0, (100 - short_score) * 0.4 + risk_score * 0.6)),
                )
            )
        return MarketMonitorHistoryResponse(as_of_date=as_of_date, points=points)

    def get_data_status(self, as_of_date: date) -> MarketMonitorDataStatusResponse:
        universe = get_market_monitor_universe()
        dataset = build_market_dataset(universe, as_of_date)
        rule_snapshot = self._build_rule_snapshot(dataset, universe)
        return MarketMonitorDataStatusResponse(
            as_of_date=as_of_date,
            source_coverage=rule_snapshot.source_coverage,
            available_sources=[
                "live_yfinance_daily",
                "nasdaq_100_static_universe",
                "fastapi_market_monitor",
            ],
            pending_sources=[
                "intraday_panic_confirmation",
                "put_call_ratio",
                "vix_term_structure",
                "calendar_events",
                "web_search_overlay",
            ],
        )

    def _build_rule_snapshot(
        self,
        dataset: dict[str, dict[str, pd.DataFrame]],
        universe: dict[str, list[str]],
    ) -> MarketMonitorRuleSnapshot:
        core_data = dataset["core"]
        missing_required = self._missing_required_symbols(core_data)
        source_coverage = self._build_source_coverage(core_data, dataset["nasdaq_100"], missing_required)
        base_event_risk_flag = self._build_base_event_risk_flag()

        if missing_required:
            return MarketMonitorRuleSnapshot(
                ready=False,
                base_event_risk_flag=base_event_risk_flag,
                source_coverage=source_coverage,
                missing_inputs=missing_required,
                degraded_factors=source_coverage.degraded_factors,
                key_indicators={},
            )

        breadth_ratio = build_breadth_ratio(dataset["nasdaq_100"])
        sector_data = {symbol: core_data[symbol] for symbol in universe["sector_etfs"] if symbol in core_data}
        long_term = summarize_score(build_long_term_series(core_data, breadth_ratio), LONG_TERM_ZONES)
        short_term = summarize_score(build_short_term_series(core_data, sector_data, breadth_ratio), SHORT_TERM_ZONES)
        system_risk = summarize_score(build_system_risk_series(core_data, breadth_ratio), SYSTEM_RISK_ZONES)
        style_effectiveness = self._build_style_effectiveness(core_data, dataset["nasdaq_100"])
        base_execution_card = self._build_execution_card(
            long_term["score"],
            short_term["score"],
            system_risk["score"],
            base_event_risk_flag,
            style_effectiveness,
        )
        panic_card = self._build_panic_card(short_term["score"], system_risk["score"])
        key_indicators = self._build_key_indicators(core_data, breadth_ratio)

        return MarketMonitorRuleSnapshot(
            ready=True,
            long_term_score=MarketScoreCard(
                score=long_term["score"],
                zone=long_term["zone"],
                delta_1d=long_term["delta_1d"],
                delta_5d=long_term["delta_5d"],
                slope_state=long_term["slope_state"],
                action=self._long_term_action(long_term["score"]),
            ),
            short_term_score=MarketScoreCard(
                score=short_term["score"],
                zone=short_term["zone"],
                delta_1d=short_term["delta_1d"],
                delta_5d=short_term["delta_5d"],
                slope_state=short_term["slope_state"],
                action=self._short_term_action(short_term["score"]),
            ),
            system_risk_score=MarketScoreCard(
                score=system_risk["score"],
                zone=system_risk["zone"],
                delta_1d=system_risk["delta_1d"],
                delta_5d=system_risk["delta_5d"],
                slope_state=system_risk["slope_state"],
                action=self._system_risk_action(system_risk["score"]),
            ),
            style_effectiveness=style_effectiveness,
            panic_reversal_score=panic_card,
            base_regime_label=base_execution_card.regime_label,
            base_execution_card=base_execution_card,
            base_event_risk_flag=base_event_risk_flag,
            source_coverage=source_coverage,
            missing_inputs=[],
            degraded_factors=source_coverage.degraded_factors,
            key_indicators=key_indicators,
        )

    def _missing_required_symbols(self, core_data: dict[str, pd.DataFrame]) -> list[str]:
        required_symbols = ["SPY", "QQQ", "IWM"]
        return [symbol for symbol in required_symbols if core_data.get(symbol) is None or core_data[symbol].empty]

    def _build_source_coverage(
        self,
        core_data: dict[str, pd.DataFrame],
        nasdaq_frames: dict[str, pd.DataFrame],
        missing_required: list[str],
    ) -> MarketSourceCoverage:
        available_core = sorted(symbol for symbol, frame in core_data.items() if frame is not None and not frame.empty)
        nasdaq_available = sum(1 for frame in nasdaq_frames.values() if frame is not None and not frame.empty)
        degraded_factors = []
        notes = [
            f"Live yfinance request completed for {len(available_core)} core/sector symbols.",
            f"Live yfinance request completed for {nasdaq_available} Nasdaq-100 symbols.",
            "Deterministic scorecards are built only from live-request data in this phase.",
        ]
        if missing_required:
            degraded_factors.append(f"missing_required_symbols:{','.join(missing_required)}")
            notes.append("Core market symbols are incomplete, so rule scorecards were not produced.")
        degraded_factors.extend(
            [
                "intraday_panic_confirmation_missing",
                "put_call_ratio_missing",
                "vix_term_structure_missing",
                "calendar_events_missing",
            ]
        )
        status = "degraded" if missing_required else "partial"
        return MarketSourceCoverage(
            status=status,
            data_freshness="live_request_yfinance_daily",
            degraded_factors=degraded_factors,
            notes=notes,
        )

    def _build_base_event_risk_flag(self) -> MarketEventRiskFlag:
        return MarketEventRiskFlag(
            index_level=MarketIndexEventRisk(active=False),
            stock_level=MarketStockEventRisk(
                earnings_stocks=[],
                rule="No event-calendar feed is connected yet. Model overlay may add event risk context.",
            ),
        )

    def _build_style_effectiveness(
        self,
        core_data: dict[str, pd.DataFrame],
        nasdaq_frames: dict[str, pd.DataFrame],
    ) -> MarketStyleEffectiveness:
        tactic_scores = score_tactic_layer(nasdaq_frames)
        asset_scores = score_asset_layer(core_data)

        top_tactic = max(tactic_scores, key=tactic_scores.get)
        avoid_tactic = min(tactic_scores, key=tactic_scores.get)
        preferred_assets = sorted(asset_scores, key=asset_scores.get, reverse=True)[:2]
        avoid_assets = sorted(asset_scores, key=asset_scores.get)[:2]

        label_map = {
            "trend_breakout": "trend_breakout",
            "dip_buy": "dip_buy",
            "oversold_bounce": "oversold_bounce",
            "large_cap_tech": "large_cap_tech",
            "small_cap_momentum": "small_cap_momentum",
            "defensive": "defensive",
            "energy_cyclical": "energy_cyclical",
            "financials": "financials",
        }

        return MarketStyleEffectiveness(
            tactic_layer=MarketStyleTacticLayer(
                trend_breakout=MarketStyleSignal(
                    score=tactic_scores["trend_breakout"],
                    valid=tactic_scores["trend_breakout"] >= 55,
                    delta_5d=0,
                ),
                dip_buy=MarketStyleSignal(
                    score=tactic_scores["dip_buy"],
                    valid=tactic_scores["dip_buy"] >= 55,
                    delta_5d=0,
                ),
                oversold_bounce=MarketStyleSignal(
                    score=tactic_scores["oversold_bounce"],
                    valid=tactic_scores["oversold_bounce"] >= 55,
                    delta_5d=0,
                ),
                top_tactic=label_map[top_tactic],
                avoid_tactic=label_map[avoid_tactic],
            ),
            asset_layer=MarketStyleAssetLayer(
                large_cap_tech=MarketStyleSignal(
                    score=asset_scores["large_cap_tech"],
                    preferred="large_cap_tech" in preferred_assets,
                    delta_5d=0,
                ),
                small_cap_momentum=MarketStyleSignal(
                    score=asset_scores["small_cap_momentum"],
                    preferred="small_cap_momentum" in preferred_assets,
                    delta_5d=0,
                ),
                defensive=MarketStyleSignal(
                    score=asset_scores["defensive"],
                    preferred="defensive" in preferred_assets,
                    delta_5d=0,
                ),
                energy_cyclical=MarketStyleSignal(
                    score=asset_scores["energy_cyclical"],
                    preferred="energy_cyclical" in preferred_assets,
                    delta_5d=0,
                ),
                financials=MarketStyleSignal(
                    score=asset_scores["financials"],
                    preferred="financials" in preferred_assets,
                    delta_5d=0,
                ),
                preferred_assets=[label_map[item] for item in preferred_assets],
                avoid_assets=[label_map[item] for item in avoid_assets],
            ),
        )

    def _build_execution_card(
        self,
        long_score: float,
        short_score: float,
        system_risk_score: float,
        event_risk_flag: MarketEventRiskFlag,
        style_effectiveness: MarketStyleEffectiveness,
    ) -> MarketExecutionCard:
        regime_label = self._regime_label(long_score, short_score, system_risk_score)
        return self._build_execution_card_for_regime(regime_label, event_risk_flag, style_effectiveness)

    def _build_execution_card_for_regime(
        self,
        regime_label: str,
        event_risk_flag: MarketEventRiskFlag,
        style_effectiveness: MarketStyleEffectiveness,
    ) -> MarketExecutionCard:
        defaults = self._execution_defaults_for_regime(regime_label)
        return MarketExecutionCard(
            regime_label=regime_label,
            conflict_mode=defaults["conflict_mode"],
            total_exposure_range=defaults["total_exposure_range"],
            new_position_allowed=defaults["new_position_allowed"],
            chase_breakout_allowed=defaults["chase_breakout_allowed"],
            dip_buy_allowed=defaults["dip_buy_allowed"],
            overnight_allowed=defaults["overnight_allowed"],
            leverage_allowed=defaults["leverage_allowed"],
            single_position_cap=defaults["single_position_cap"],
            daily_risk_budget=defaults["daily_risk_budget"],
            tactic_preference=f"{style_effectiveness.tactic_layer.top_tactic}>{style_effectiveness.tactic_layer.avoid_tactic}",
            preferred_assets=style_effectiveness.asset_layer.preferred_assets,
            avoid_assets=style_effectiveness.asset_layer.avoid_assets,
            signal_confirmation=MarketExecutionSignalConfirmation(
                current_regime_days=1,
                downgrade_unlock_in_days=2,
                note="Persistence logic is not enabled yet in phase 1.",
            ),
            event_risk_flag=event_risk_flag,
            summary=defaults["summary"],
        )

    def _execution_defaults_for_regime(self, regime_label: str) -> dict[str, Any]:
        if regime_label == "green":
            return {
                "total_exposure_range": "70%-90%",
                "conflict_mode": "trend_and_tape_aligned",
                "daily_risk_budget": "1.25R",
                "chase_breakout_allowed": True,
                "dip_buy_allowed": True,
                "new_position_allowed": True,
                "overnight_allowed": True,
                "leverage_allowed": True,
                "single_position_cap": "12%",
                "summary": "Rules support offensive trend participation.",
            }
        elif regime_label == "yellow_green_swing":
            return {
                "total_exposure_range": "50%-70%",
                "conflict_mode": "swing_window_open",
                "daily_risk_budget": "1.0R",
                "chase_breakout_allowed": True,
                "dip_buy_allowed": True,
                "new_position_allowed": True,
                "overnight_allowed": True,
                "leverage_allowed": False,
                "single_position_cap": "12%",
                "summary": "Rules favor active swing trading over heavy trend exposure.",
            }
        elif regime_label == "yellow":
            return {
                "total_exposure_range": "40%-60%",
                "conflict_mode": "conditional_offense",
                "daily_risk_budget": "0.9R",
                "chase_breakout_allowed": False,
                "dip_buy_allowed": True,
                "new_position_allowed": True,
                "overnight_allowed": True,
                "leverage_allowed": False,
                "single_position_cap": "10%",
                "summary": "Rules allow selective offense after confirmation.",
            }
        elif regime_label == "orange":
            return {
                "total_exposure_range": "25%-45%",
                "conflict_mode": "defense_first",
                "daily_risk_budget": "0.75R",
                "chase_breakout_allowed": False,
                "dip_buy_allowed": True,
                "new_position_allowed": True,
                "overnight_allowed": True,
                "leverage_allowed": False,
                "single_position_cap": "8%",
                "summary": "Rules prefer reduced size and defensive posture.",
            }
        return {
            "total_exposure_range": "0%-20%",
            "conflict_mode": "capital_protection",
            "daily_risk_budget": "0.25R",
            "chase_breakout_allowed": False,
            "dip_buy_allowed": False,
            "new_position_allowed": False,
            "overnight_allowed": False,
            "leverage_allowed": False,
            "single_position_cap": "5%",
            "summary": "Rules prioritize capital preservation.",
        }

    def _build_panic_card(self, short_score: float, system_risk_score: float) -> MarketPanicReversalCard:
        panic_gate = short_score < 35 and system_risk_score >= 45
        early_gate = short_score < 25 and system_risk_score >= 60

        if not panic_gate:
            panic_extreme = 25.0
            selling_exhaustion = 20.0
            intraday_reversal = 15.0
            followthrough = 15.0
            score = 25.0
            state = "none"
            zone = "inactive"
            action = "No panic-reversal setup is active."
        else:
            panic_extreme = max(35.0, min(100.0, 65 + (35 - short_score) * 0.9 + (system_risk_score - 45) * 0.7))
            selling_exhaustion = max(25.0, min(100.0, 25 + (system_risk_score - short_score) * 0.45))
            intraday_reversal = max(20.0, min(100.0, 15 + (35 - short_score) * 1.1))
            followthrough = max(20.0, min(100.0, 15 + (35 - short_score) * 0.8 + max(0.0, system_risk_score - 55) * 0.2))
            score = panic_extreme * 0.4 + selling_exhaustion * 0.3 + max(intraday_reversal, followthrough) * 0.3
            if panic_extreme >= 80 or score >= 50:
                state = "confirmed"
                zone = "actionable"
                action = "Rule engine sees a tradeable panic reversal setup, but confirmation is still daily-only."
            else:
                state = "watch"
                zone = "watch"
                action = "Rule engine sees panic conditions, but confirmation remains incomplete."

        return MarketPanicReversalCard(
            score=round(score, 1),
            zone=zone,
            state=state,
            panic_extreme_score=round(panic_extreme, 1),
            selling_exhaustion_score=round(selling_exhaustion, 1),
            intraday_reversal_score=round(intraday_reversal, 1),
            followthrough_confirmation_score=round(followthrough, 1),
            action=action,
            system_risk_override="When system risk is extreme, panic-reversal exposure should stay capped.",
            stop_loss="ATR x 1.0",
            profit_rule="Take 50% at 1R and trail the remainder at breakeven.",
            timeout_warning=False,
            days_held=0,
            early_entry_allowed=state == "confirmed" and early_gate and intraday_reversal >= 60,
        )

    def _build_key_indicators(self, core_data: dict[str, pd.DataFrame], breadth_ratio: pd.Series) -> dict[str, Any]:
        spy_close = self._last_value(core_data["SPY"], "Close")
        qqq_close = self._last_value(core_data["QQQ"], "Close")
        iwm_close = self._last_value(core_data["IWM"], "Close")
        vix_close = self._last_value(core_data.get("^VIX", pd.DataFrame()), "Close")
        breadth = float(breadth_ratio.dropna().iloc[-1]) if not breadth_ratio.dropna().empty else None
        return {
            "spy_close": spy_close,
            "qqq_close": qqq_close,
            "iwm_close": iwm_close,
            "vix_close": vix_close,
            "breadth_above_200dma_pct": breadth,
        }

    def _last_value(self, frame: pd.DataFrame, column: str) -> float | None:
        series = frame.get(column)
        if series is None:
            return None
        clean = series.dropna()
        if clean.empty:
            return None
        return float(clean.iloc[-1])

    def _build_context_queries(self, rule_snapshot: MarketMonitorRuleSnapshot) -> list[str]:
        queries = [
            "What macro events are most relevant to US equities today or next 3 trading days?",
            "Are there any major earnings, policy, geopolitical, or regulatory events affecting SPY, QQQ, IWM, or mega-cap tech today?",
        ]
        if rule_snapshot.degraded_factors:
            queries.append(
                "Do recent sources explain elevated market risk or degraded breadth conditions for US equities?"
            )
        if rule_snapshot.base_regime_label in {"orange", "red"}:
            queries.append(
                "Are there current catalysts that justify a defensive or risk-off stance in US equities?"
            )
        if rule_snapshot.base_regime_label == "yellow_green_swing":
            queries.append(
                "Is there evidence of sector rotation or short-term swing conditions in US equities right now?"
            )
        return queries

    def _merge_overlay(
        self,
        rule_snapshot: MarketMonitorRuleSnapshot,
        model_overlay: MarketMonitorModelOverlay,
    ) -> MarketExecutionCard | None:
        base_event_risk_flag = rule_snapshot.base_event_risk_flag
        final_event_risk_flag = model_overlay.event_risk_override or base_event_risk_flag
        if not rule_snapshot.base_execution_card:
            return None

        adjustments = model_overlay.execution_adjustments
        target_regime = (
            adjustments.regime_label
            if adjustments and adjustments.regime_label
            else model_overlay.regime_override or rule_snapshot.base_execution_card.regime_label
        )
        rebuilt_card = self._build_execution_card_for_regime(
            target_regime,
            final_event_risk_flag,
            rule_snapshot.style_effectiveness,
        )
        payload = deepcopy(rebuilt_card.model_dump(mode="python"))
        if adjustments:
            for field, value in adjustments.model_dump(exclude_none=True).items():
                payload[field] = value
        payload["event_risk_flag"] = final_event_risk_flag.model_dump(mode="python")
        return MarketExecutionCard.model_validate(payload)

    def _regime_label(self, long_score: float, short_score: float, system_risk_score: float) -> str:
        if system_risk_score > 70 or long_score < 35:
            return "red"
        if 45 <= long_score < 65 and short_score >= 60 and system_risk_score <= 35:
            return "yellow_green_swing"
        if long_score >= 65 and short_score >= 55 and system_risk_score <= 35:
            return "green"
        if long_score >= 50 and short_score >= 45 and system_risk_score <= 50:
            return "yellow"
        return "orange"

    def _long_term_action(self, score: float) -> str:
        if score >= 80:
            return "Strong long-term backdrop for trend exposure."
        if score >= 65:
            return "Healthy intermediate trend; add risk selectively."
        if score >= 50:
            return "Intermediate trend is constructive but not fully confirmed."
        if score >= 35:
            return "Long-term backdrop is cautious; keep exposure moderate."
        return "Long-term backdrop is defensive; avoid heavy trend risk."

    def _short_term_action(self, score: float) -> str:
        if score >= 80:
            return "Short-term conditions are highly tradeable."
        if score >= 65:
            return "Short-term tape is active; increase selectivity, not recklessness."
        if score >= 50:
            return "Short-term setup is workable for dip buys and confirmed breakouts."
        if score >= 35:
            return "Short-term setup is watchful rather than aggressive."
        return "Short-term setup is weak; avoid chasing and overnight volatility."

    def _system_risk_action(self, score: float) -> str:
        if score >= 80:
            return "Systemic risk is elevated; protect capital first."
        if score >= 60:
            return "Risk pressure is high; cut gross exposure and avoid leverage."
        if score >= 45:
            return "Risk is elevated; tighten risk budgets and reduce chasing."
        if score >= 20:
            return "System risk is normal; use standard controls."
        return "System risk is benign relative to the recent range."
