from __future__ import annotations

from typing import Callable

from tradingagents.web.market_monitor.prompts import build_execution_prompt
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorExecutionCard,
    MarketMonitorEventRiskFlag,
    MarketMonitorFactSheet,
    MarketMonitorRunLlmConfig,
    MarketMonitorScoreCard,
    MarketMonitorSignalConfirmation,
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
        event_risk: MarketMonitorEventRiskFlag,
        fallback: Callable[[], MarketMonitorExecutionCard],
    ) -> InferenceResult[MarketMonitorExecutionCard]:
        system_prompt, user_prompt, input_summary = build_execution_prompt(
            fact_sheet,
            long_term,
            short_term,
            system_risk,
            style,
            event_risk,
        )
        return self.runner.run_json_inference(
            stage="execution_aggregation",
            card_type="execution",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=self._parse_execution,
            fallback=fallback,
        )

    @staticmethod
    def _parse_execution(payload: dict) -> MarketMonitorExecutionCard:
        signal_confirmation = payload.get("signal_confirmation") or {}
        return MarketMonitorExecutionCard(
            regime_label=payload["regime_label"],
            conflict_mode=payload["conflict_mode"],
            total_exposure_range=payload["total_exposure_range"],
            new_position_allowed=bool(payload["new_position_allowed"]),
            chase_breakout_allowed=bool(payload["chase_breakout_allowed"]),
            dip_buy_allowed=bool(payload["dip_buy_allowed"]),
            overnight_allowed=bool(payload["overnight_allowed"]),
            leverage_allowed=bool(payload["leverage_allowed"]),
            single_position_cap=payload["single_position_cap"],
            daily_risk_budget=payload["daily_risk_budget"],
            tactic_preference=payload["tactic_preference"],
            preferred_assets=list(payload.get("preferred_assets") or []),
            avoid_assets=list(payload.get("avoid_assets") or []),
            signal_confirmation=MarketMonitorSignalConfirmation(
                current_regime_observations=int(signal_confirmation.get("current_regime_observations", 1)),
                risk_loosening_unlock_in_observations=int(signal_confirmation.get("risk_loosening_unlock_in_observations", 2)),
                note=signal_confirmation.get("note") or "当前 regime 为新近状态；若要放宽风险边界，需再连续观察 2 次刷新保持。",
            ),
            event_risk_flag=MarketMonitorEventRiskFlag.model_validate(payload.get("event_risk_flag") or {}),
            summary=payload["summary"],
            reasoning_summary=payload.get("reasoning_summary"),
            key_drivers=list(payload.get("key_drivers") or []),
            risks=list(payload.get("risks") or []),
            confidence=payload.get("confidence"),
        )
