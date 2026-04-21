from __future__ import annotations

from typing import Callable

from tradingagents.web.market_monitor.prompts import (
    build_event_risk_prompt,
    build_long_term_prompt,
    build_panic_prompt,
    build_short_term_prompt,
    build_style_prompt,
    build_system_risk_prompt,
)
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorActionModifier,
    MarketMonitorEventRiskFlag,
    MarketMonitorFactSheet,
    MarketMonitorIndexEventRisk,
    MarketMonitorLayerMetric,
    MarketMonitorPanicCard,
    MarketMonitorRunLlmConfig,
    MarketMonitorScoreCard,
    MarketMonitorStockEventRisk,
    MarketMonitorStyleAssetLayer,
    MarketMonitorStyleEffectiveness,
    MarketMonitorStyleTacticLayer,
    MarketMonitorSystemRiskCard,
)

from .base import InferenceResult, MarketMonitorInferenceRunner


class MarketMonitorCardInferenceService:
    def __init__(self, llm_config: MarketMonitorRunLlmConfig | None = None) -> None:
        self.runner = MarketMonitorInferenceRunner(llm_config)

    def infer_long_term(
        self,
        fact_sheet: MarketMonitorFactSheet,
        fallback: Callable[[], MarketMonitorScoreCard],
    ) -> InferenceResult[MarketMonitorScoreCard]:
        system_prompt, user_prompt, input_summary = build_long_term_prompt(fact_sheet)
        return self.runner.run_json_inference(
            stage="card_inference",
            card_type="long_term",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=lambda payload: MarketMonitorScoreCard.model_validate(payload),
            fallback=fallback,
        )

    def infer_short_term(
        self,
        fact_sheet: MarketMonitorFactSheet,
        fallback: Callable[[], MarketMonitorScoreCard],
    ) -> InferenceResult[MarketMonitorScoreCard]:
        system_prompt, user_prompt, input_summary = build_short_term_prompt(fact_sheet)
        return self.runner.run_json_inference(
            stage="card_inference",
            card_type="short_term",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=lambda payload: MarketMonitorScoreCard.model_validate(payload),
            fallback=fallback,
        )

    def infer_system_risk(
        self,
        fact_sheet: MarketMonitorFactSheet,
        fallback: Callable[[], MarketMonitorSystemRiskCard],
    ) -> InferenceResult[MarketMonitorSystemRiskCard]:
        system_prompt, user_prompt, input_summary = build_system_risk_prompt(fact_sheet)
        return self.runner.run_json_inference(
            stage="card_inference",
            card_type="system_risk",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=lambda payload: MarketMonitorSystemRiskCard.model_validate(payload),
            fallback=fallback,
        )

    def infer_style(
        self,
        fact_sheet: MarketMonitorFactSheet,
        fallback: Callable[[], MarketMonitorStyleEffectiveness],
    ) -> InferenceResult[MarketMonitorStyleEffectiveness]:
        system_prompt, user_prompt, input_summary = build_style_prompt(fact_sheet)
        return self.runner.run_json_inference(
            stage="card_inference",
            card_type="style",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=self._parse_style,
            fallback=fallback,
        )

    def infer_event_risk(
        self,
        fact_sheet: MarketMonitorFactSheet,
        fallback: Callable[[], MarketMonitorEventRiskFlag],
    ) -> InferenceResult[MarketMonitorEventRiskFlag]:
        system_prompt, user_prompt, input_summary = build_event_risk_prompt(fact_sheet)
        return self.runner.run_json_inference(
            stage="card_inference",
            card_type="event_risk",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=self._parse_event_risk,
            fallback=fallback,
        )

    def infer_panic(
        self,
        fact_sheet: MarketMonitorFactSheet,
        fallback: Callable[[], MarketMonitorPanicCard],
    ) -> InferenceResult[MarketMonitorPanicCard]:
        system_prompt, user_prompt, input_summary = build_panic_prompt(fact_sheet)
        return self.runner.run_json_inference(
            stage="card_inference",
            card_type="panic",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=lambda payload: MarketMonitorPanicCard.model_validate(payload),
            fallback=fallback,
        )

    @staticmethod
    def _parse_event_risk(payload: dict) -> MarketMonitorEventRiskFlag:
        index_level = payload.get("index_level") or {}
        stock_level = payload.get("stock_level") or {}
        return MarketMonitorEventRiskFlag(
            index_level=MarketMonitorIndexEventRisk(
                active=bool(index_level.get("active", False)),
                type=index_level.get("type"),
                days_to_event=index_level.get("days_to_event"),
                action_modifier=MarketMonitorActionModifier.model_validate(index_level.get("action_modifier") or {}),
            ),
            stock_level=MarketMonitorStockEventRisk(
                earnings_stocks=list(stock_level.get("earnings_stocks") or []),
                rule=stock_level.get("rule"),
            ),
            reasoning_summary=payload.get("reasoning_summary"),
            key_drivers=list(payload.get("key_drivers") or []),
            risks=list(payload.get("risks") or []),
            confidence=payload.get("confidence"),
        )

    @staticmethod
    def _parse_style(payload: dict) -> MarketMonitorStyleEffectiveness:
        tactic_layer = payload.get("tactic_layer") or {}
        asset_layer = payload.get("asset_layer") or {}
        return MarketMonitorStyleEffectiveness(
            tactic_layer=MarketMonitorStyleTacticLayer(
                trend_breakout=MarketMonitorLayerMetric.model_validate(tactic_layer.get("trend_breakout") or {}),
                dip_buy=MarketMonitorLayerMetric.model_validate(tactic_layer.get("dip_buy") or {}),
                oversold_bounce=MarketMonitorLayerMetric.model_validate(tactic_layer.get("oversold_bounce") or {}),
                top_tactic=tactic_layer.get("top_tactic") or "回调低吸",
                avoid_tactic=tactic_layer.get("avoid_tactic") or "趋势突破",
            ),
            asset_layer=MarketMonitorStyleAssetLayer(
                large_cap_tech=MarketMonitorLayerMetric.model_validate(asset_layer.get("large_cap_tech") or {}),
                small_cap_momentum=MarketMonitorLayerMetric.model_validate(asset_layer.get("small_cap_momentum") or {}),
                defensive=MarketMonitorLayerMetric.model_validate(asset_layer.get("defensive") or {}),
                energy_cyclical=MarketMonitorLayerMetric.model_validate(asset_layer.get("energy_cyclical") or {}),
                financials=MarketMonitorLayerMetric.model_validate(asset_layer.get("financials") or {}),
                preferred_assets=list(asset_layer.get("preferred_assets") or []),
                avoid_assets=list(asset_layer.get("avoid_assets") or []),
            ),
            reasoning_summary=payload.get("reasoning_summary"),
            key_drivers=list(payload.get("key_drivers") or []),
            risks=list(payload.get("risks") or []),
            confidence=payload.get("confidence"),
        )
