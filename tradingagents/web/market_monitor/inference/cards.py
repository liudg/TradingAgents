from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from tradingagents.web.market_monitor.indicators import bounded_score
from tradingagents.web.market_monitor.prompts import (
    build_event_risk_prompt,
    build_long_term_prompt,
    build_panic_prompt,
    build_short_term_prompt,
    build_style_prompt,
    build_system_risk_prompt,
)
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorEventRiskFlag,
    MarketMonitorFactSheet,
    MarketMonitorPanicCard,
    MarketMonitorRunLlmConfig,
    MarketMonitorScoreAdjustment,
    MarketMonitorScoreCard,
    MarketMonitorStyleEffectiveness,
    MarketMonitorSystemRiskCard,
)

from .base import InferenceResult, MarketMonitorInferenceRunner, normalize_reasoning_updates


class MarketMonitorCardInferenceService:
    def __init__(self, llm_config: MarketMonitorRunLlmConfig | None = None) -> None:
        self.runner = MarketMonitorInferenceRunner(llm_config)

    def infer_long_term(
        self,
        fact_sheet: MarketMonitorFactSheet,
        deterministic_card: MarketMonitorScoreCard,
        fallback: Callable[[], MarketMonitorScoreCard],
    ) -> InferenceResult[MarketMonitorScoreCard]:
        system_prompt, user_prompt, input_summary = build_long_term_prompt(fact_sheet, deterministic_card)
        return self.runner.run_json_inference(
            stage="card_judgment",
            card_type="long_term",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=lambda payload: _parse_score_card(payload, deterministic_card, fact_sheet),
            fallback=fallback,
        )

    def infer_short_term(
        self,
        fact_sheet: MarketMonitorFactSheet,
        deterministic_card: MarketMonitorScoreCard,
        fallback: Callable[[], MarketMonitorScoreCard],
    ) -> InferenceResult[MarketMonitorScoreCard]:
        system_prompt, user_prompt, input_summary = build_short_term_prompt(fact_sheet, deterministic_card)
        return self.runner.run_json_inference(
            stage="card_judgment",
            card_type="short_term",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=lambda payload: _parse_score_card(payload, deterministic_card, fact_sheet),
            fallback=fallback,
        )

    def infer_system_risk(
        self,
        fact_sheet: MarketMonitorFactSheet,
        deterministic_card: MarketMonitorSystemRiskCard,
        fallback: Callable[[], MarketMonitorSystemRiskCard],
    ) -> InferenceResult[MarketMonitorSystemRiskCard]:
        system_prompt, user_prompt, input_summary = build_system_risk_prompt(fact_sheet, deterministic_card)
        return self.runner.run_json_inference(
            stage="card_judgment",
            card_type="system_risk",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=lambda payload: _parse_system_risk_card(payload, deterministic_card, fact_sheet),
            fallback=fallback,
        )

    def infer_style(
        self,
        fact_sheet: MarketMonitorFactSheet,
        deterministic_card: MarketMonitorStyleEffectiveness,
        fallback: Callable[[], MarketMonitorStyleEffectiveness],
    ) -> InferenceResult[MarketMonitorStyleEffectiveness]:
        system_prompt, user_prompt, input_summary = build_style_prompt(fact_sheet, deterministic_card)
        return self.runner.run_json_inference(
            stage="card_judgment",
            card_type="style",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=lambda payload: _parse_style_card(payload, deterministic_card),
            fallback=fallback,
        )

    def infer_event_risk(
        self,
        fact_sheet: MarketMonitorFactSheet,
        deterministic_card: MarketMonitorEventRiskFlag,
        fallback: Callable[[], MarketMonitorEventRiskFlag],
    ) -> InferenceResult[MarketMonitorEventRiskFlag]:
        system_prompt, user_prompt, input_summary = build_event_risk_prompt(fact_sheet, deterministic_card)
        return self.runner.run_json_inference(
            stage="card_judgment",
            card_type="event_risk",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=lambda payload: MarketMonitorEventRiskFlag.model_validate(payload),
            fallback=fallback,
        )

    def infer_panic(
        self,
        fact_sheet: MarketMonitorFactSheet,
        deterministic_card: MarketMonitorPanicCard,
        fallback: Callable[[], MarketMonitorPanicCard],
    ) -> InferenceResult[MarketMonitorPanicCard]:
        system_prompt, user_prompt, input_summary = build_panic_prompt(fact_sheet, deterministic_card)
        return self.runner.run_json_inference(
            stage="card_judgment",
            card_type="panic",
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            input_summary=input_summary,
            parser=lambda payload: _enforce_panic_card(MarketMonitorPanicCard.model_validate(payload), deterministic_card),
            fallback=fallback,
        )


def _parse_score_card(
    payload: dict[str, Any],
    deterministic_card: MarketMonitorScoreCard,
    fact_sheet: MarketMonitorFactSheet,
) -> MarketMonitorScoreCard:
    candidate = deterministic_card.model_dump(mode="json")
    candidate.update(normalize_reasoning_updates(payload))
    if "score_adjustment" in payload:
        candidate["score_adjustment"] = _normalize_score_adjustment(payload.get("score_adjustment"))
    card = MarketMonitorScoreCard.model_validate(candidate)
    return _enforce_score_card(card, deterministic_card, fact_sheet)


def _parse_system_risk_card(
    payload: dict[str, Any],
    deterministic_card: MarketMonitorSystemRiskCard,
    fact_sheet: MarketMonitorFactSheet,
) -> MarketMonitorSystemRiskCard:
    candidate = deterministic_card.model_dump(mode="json")
    candidate.update(normalize_reasoning_updates(payload))
    if "score_adjustment" in payload:
        candidate["score_adjustment"] = _normalize_score_adjustment(payload.get("score_adjustment"))
    card = MarketMonitorSystemRiskCard.model_validate(candidate)
    return _enforce_system_risk_card(card, deterministic_card, fact_sheet)


def _parse_style_card(
    payload: dict[str, Any],
    deterministic_card: MarketMonitorStyleEffectiveness,
) -> MarketMonitorStyleEffectiveness:
    candidate = deterministic_card.model_dump(mode="json")
    candidate.update(normalize_reasoning_updates(payload))
    if "score_adjustment" in payload:
        candidate["score_adjustment"] = _normalize_score_adjustment(payload.get("score_adjustment"))
    card = MarketMonitorStyleEffectiveness.model_validate(candidate)
    return _enforce_style_card(card, deterministic_card)


def _normalize_score_adjustment(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    candidate = dict(raw)
    if "value" not in candidate and "adjustment" in candidate:
        candidate["value"] = candidate["adjustment"]
    if "direction" not in candidate:
        try:
            value = float(candidate.get("value"))
        except (TypeError, ValueError):
            return None
        candidate["direction"] = "up" if value > 0 else "down" if value < 0 else "flat"
    if isinstance(candidate.get("source_event_ids"), str):
        candidate["source_event_ids"] = [candidate["source_event_ids"]]
    if isinstance(candidate.get("source_factors"), str):
        candidate["source_factors"] = [candidate["source_factors"]]
    try:
        return MarketMonitorScoreAdjustment.model_validate(candidate).model_dump(mode="json")
    except ValueError:
        return None


def _enforce_score_card(
    card: MarketMonitorScoreCard,
    deterministic_card: MarketMonitorScoreCard,
    fact_sheet: MarketMonitorFactSheet,
) -> MarketMonitorScoreCard:
    adjustment = _bounded_adjustment(card.score_adjustment, fact_sheet)
    score = deterministic_card.deterministic_score
    if adjustment is not None:
        score = bounded_score(score + adjustment.value)
    return card.model_copy(update={
        "deterministic_score": deterministic_card.deterministic_score,
        "score": round(score, 1),
        "factor_breakdown": deterministic_card.factor_breakdown,
        "score_adjustment": adjustment,
    })


def _enforce_system_risk_card(
    card: MarketMonitorSystemRiskCard,
    deterministic_card: MarketMonitorSystemRiskCard,
    fact_sheet: MarketMonitorFactSheet,
) -> MarketMonitorSystemRiskCard:
    adjusted = _enforce_score_card(card, deterministic_card, fact_sheet)
    return MarketMonitorSystemRiskCard.model_validate(adjusted.model_dump(mode="json") | {
        "liquidity_stress_score": deterministic_card.liquidity_stress_score,
        "risk_appetite_score": deterministic_card.risk_appetite_score,
        "event_triggers": _validate_event_triggers(deterministic_card.event_triggers, fact_sheet),
    })


def _enforce_style_card(card: MarketMonitorStyleEffectiveness, deterministic_card: MarketMonitorStyleEffectiveness) -> MarketMonitorStyleEffectiveness:
    adjustment = _bounded_adjustment(card.score_adjustment, None)
    score = deterministic_card.deterministic_score
    if adjustment is not None:
        score = bounded_score(score + adjustment.value)
    return card.model_copy(update={
        "deterministic_score": deterministic_card.deterministic_score,
        "score": round(score, 1),
        "score_adjustment": adjustment,
        "tactic_layer": deterministic_card.tactic_layer,
        "asset_layer": deterministic_card.asset_layer,
    })


def _enforce_panic_card(card: MarketMonitorPanicCard, deterministic_card: MarketMonitorPanicCard) -> MarketMonitorPanicCard:
    adjustment = _bounded_adjustment(card.score_adjustment, None)
    score = deterministic_card.deterministic_score
    if adjustment is not None:
        score = bounded_score(score + adjustment.value)
    return card.model_copy(update={
        "deterministic_score": deterministic_card.deterministic_score,
        "score": round(score, 1),
        "score_adjustment": adjustment,
        "zone": deterministic_card.zone,
        "state": deterministic_card.state,
        "panic_extreme_score": deterministic_card.panic_extreme_score,
        "selling_exhaustion_score": deterministic_card.selling_exhaustion_score,
        "reversal_confirmation_score": deterministic_card.reversal_confirmation_score,
        "factor_breakdown": deterministic_card.factor_breakdown,
        "early_entry_allowed": deterministic_card.early_entry_allowed,
        "max_position_hint": deterministic_card.max_position_hint,
    })


def _bounded_adjustment(
    adjustment: MarketMonitorScoreAdjustment | None,
    fact_sheet: MarketMonitorFactSheet | None,
) -> MarketMonitorScoreAdjustment | None:
    if adjustment is None:
        return None
    value = max(-5.0, min(5.0, float(adjustment.value)))
    if value == 0 or not adjustment.reason.strip():
        return None
    if _direction_conflicts(value, adjustment.direction):
        return None
    expires_at = adjustment.expires_at
    if adjustment.source_event_ids:
        if fact_sheet is None:
            return None
        events_by_id = {event.event_id: event for event in fact_sheet.event_fact_sheet}
        source_events = [events_by_id.get(event_id) for event_id in adjustment.source_event_ids]
        if any(event is None for event in source_events):
            return None
        valid_events = [event for event in source_events if event is not None and event.expires_at > fact_sheet.generated_at]
        if not valid_events:
            return None
        earliest_expiry = min(event.expires_at for event in valid_events)
        expires_at = _min_datetime(expires_at, earliest_expiry) if expires_at else earliest_expiry
    elif not adjustment.source_factors:
        return None
    confidence = max(0.0, min(1.0, float(adjustment.confidence)))
    return adjustment.model_copy(update={
        "value": round(value, 1),
        "confidence": round(confidence, 2),
        "expires_at": expires_at,
    })


def _direction_conflicts(value: float, direction: str) -> bool:
    normalized = direction.lower().strip()
    if value > 0:
        return normalized in {"down", "risk_down", "lower", "negative"}
    return normalized in {"up", "risk_up", "higher", "positive"}


def _min_datetime(left: datetime, right: datetime) -> datetime:
    return left if left <= right else right


def _validate_event_triggers(triggers: list, fact_sheet: MarketMonitorFactSheet) -> list:
    events_by_id = {event.event_id: event for event in fact_sheet.event_fact_sheet}
    valid = []
    for trigger in triggers:
        if trigger.trigger_type == "event_fact":
            if not trigger.source_event_ids:
                continue
            source_events = [events_by_id.get(event_id) for event_id in trigger.source_event_ids]
            if any(event is None or event.expires_at <= fact_sheet.generated_at for event in source_events):
                continue
        elif trigger.trigger_type == "market_structure":
            if trigger.source_event_ids:
                continue
        if trigger.expires_at is None or trigger.expires_at <= fact_sheet.generated_at:
            continue
        valid.append(trigger)
    return valid
