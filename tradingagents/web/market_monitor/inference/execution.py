from __future__ import annotations

from typing import Callable

from tradingagents.web.market_monitor.prompts import build_execution_prompt
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorEventFact,
    MarketMonitorExecutionCard,
    MarketMonitorFactSheet,
    MarketMonitorPanicCard,
    MarketMonitorRunLlmConfig,
    MarketMonitorScoreCard,
    MarketMonitorStyleEffectiveness,
    MarketMonitorSystemRiskCard,
)

from .base import InferenceResult, MarketMonitorInferenceRunner


class MarketMonitorExecutionInferenceService:
    def __init__(self, llm_config: MarketMonitorRunLlmConfig | None = None) -> None:
        self.runner = MarketMonitorInferenceRunner(llm_config)

    def infer_execution(
        self,
        *,
        fact_sheet: MarketMonitorFactSheet,
        long_term: MarketMonitorScoreCard,
        short_term: MarketMonitorScoreCard,
        system_risk: MarketMonitorSystemRiskCard,
        style: MarketMonitorStyleEffectiveness,
        panic: MarketMonitorPanicCard,
        event_fact_sheet: list[MarketMonitorEventFact],
        fallback: Callable[[], MarketMonitorExecutionCard],
    ) -> InferenceResult[MarketMonitorExecutionCard]:
        system_prompt, user_prompt, input_summary = build_execution_prompt(
            fact_sheet,
            long_term,
            short_term,
            system_risk,
            style,
            panic,
            event_fact_sheet,
        )
        return self.runner.run_json_inference(
            stage="execution_decision",
            card_type="execution",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=lambda payload: _enforce_execution_card(MarketMonitorExecutionCard.model_validate(payload), fallback()),
            fallback=fallback,
        )


def _enforce_execution_card(card: MarketMonitorExecutionCard, baseline: MarketMonitorExecutionCard) -> MarketMonitorExecutionCard:
    risks = list(dict.fromkeys([*baseline.risks, *card.risks]))
    key_drivers = card.key_drivers or baseline.key_drivers
    confidence = min(card.confidence, baseline.confidence)
    return card.model_copy(update={
        "regime_label": baseline.regime_label,
        "conflict_mode": baseline.conflict_mode,
        "total_exposure_range": baseline.total_exposure_range,
        "new_position_allowed": baseline.new_position_allowed,
        "chase_breakout_allowed": baseline.chase_breakout_allowed,
        "dip_buy_allowed": baseline.dip_buy_allowed,
        "overnight_allowed": baseline.overnight_allowed,
        "leverage_allowed": baseline.leverage_allowed,
        "single_position_cap": baseline.single_position_cap,
        "daily_risk_budget": baseline.daily_risk_budget,
        "tactic_preference": baseline.tactic_preference,
        "preferred_assets": baseline.preferred_assets,
        "avoid_assets": baseline.avoid_assets,
        "signal_confirmation": baseline.signal_confirmation,
        "event_risk_flag": baseline.event_risk_flag,
        "confidence": confidence,
        "risks": risks,
        "key_drivers": key_drivers,
    })
