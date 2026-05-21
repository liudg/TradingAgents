from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients import create_llm_client
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorPromptTrace,
    MarketMonitorRunLlmConfig,
)

T = TypeVar("T")


@dataclass
class InferenceResult(Generic[T]):
    payload: T
    trace: MarketMonitorPromptTrace
    used_fallback: bool = False


def normalize_reasoning_updates(payload: dict[str, Any]) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    for field in ("score_reasoning", "action_hint", "decision_reasoning"):
        value = payload.get(field)
        if isinstance(value, str) and value.strip():
            updates[field] = value.strip()
    risks = _normalize_string_list(payload.get("risks"))
    if risks is not None:
        updates["risks"] = risks
    evidence = _normalize_evidence_refs(payload.get("evidence"))
    if evidence is not None:
        updates["evidence"] = evidence
    if "confidence" in payload:
        try:
            updates["confidence"] = round(max(0.0, min(1.0, float(payload["confidence"]))), 2)
        except (TypeError, ValueError):
            pass
    return updates


def _normalize_string_list(value: Any) -> list[str] | None:
    if isinstance(value, list):
        values = [_normalize_string_item(item) for item in value]
        return [item for item in values if item]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return None


def _normalize_string_item(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("risk", "driver", "summary", "reason", "text", "label", "name"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
    text = str(value).strip()
    return text or None


def _normalize_evidence_refs(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    refs = []
    for item in value:
        if not isinstance(item, dict):
            continue
        source_type = _string_or_none(item.get("source_type") or item.get("type") or item.get("source"))
        source_label = _string_or_none(
            item.get("source_label")
            or item.get("source_name")
            or item.get("label")
            or item.get("name")
            or item.get("id")
            or item.get("factor")
            or item.get("metric")
        )
        if not source_type or not source_label:
            continue
        ref: dict[str, Any] = {
            "source_type": source_type,
            "source_label": source_label,
            "snippet": _string_or_none(item.get("snippet") or item.get("summary") or item.get("reason")),
            "timestamp": item.get("timestamp") or item.get("observed_at"),
            "confidence": item.get("confidence"),
        }
        if isinstance(item.get("metadata"), dict):
            ref["metadata"] = item["metadata"]
        refs.append(ref)
    return refs


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class MarketMonitorInferenceRunner:
    def __init__(self, llm_config: MarketMonitorRunLlmConfig | None = None) -> None:
        config = llm_config or MarketMonitorRunLlmConfig(
            provider=DEFAULT_CONFIG["llm_provider"],
            model=DEFAULT_CONFIG["deep_think_llm"],
            reasoning_effort=(
                DEFAULT_CONFIG.get("codex_reasoning_effort")
                if DEFAULT_CONFIG["llm_provider"] == "codex"
                else DEFAULT_CONFIG.get("openai_reasoning_effort")
                if DEFAULT_CONFIG["llm_provider"] == "openai"
                else DEFAULT_CONFIG.get("anthropic_effort")
                if DEFAULT_CONFIG["llm_provider"] == "anthropic"
                else None
            ),
        )
        self.llm_config = config
        self.llm = self._create_llm(config)

    def _create_llm(self, config: MarketMonitorRunLlmConfig):
        kwargs: dict[str, Any] = {}
        provider = (config.provider or DEFAULT_CONFIG["llm_provider"]).lower()
        if provider in {"openai", "codex"} and config.reasoning_effort:
            kwargs["reasoning_effort"] = config.reasoning_effort
        elif provider == "anthropic" and config.reasoning_effort:
            kwargs["effort"] = config.reasoning_effort
        client = create_llm_client(
            provider=provider,
            model=config.model or DEFAULT_CONFIG["deep_think_llm"],
            base_url=DEFAULT_CONFIG.get("backend_url"),
            **kwargs,
        )
        return client.get_llm()

    def run_json_inference(
        self,
        *,
        stage: str,
        card_type: str,
        system_prompt: str,
        user_prompt: str,
        parser: Callable[[dict[str, Any]], T],
        fallback: Callable[[], T],
        input_summary: str,
    ) -> InferenceResult[T]:
        started = time.perf_counter()
        prompt_text = f"SYSTEM:\n{system_prompt}\n\nUSER:\n{user_prompt}"
        raw_response = None
        parsed_ok = False
        error = None
        used_fallback = False
        token_usage: dict[str, int] = {}
        try:
            response = self.llm.invoke([
                ("system", system_prompt),
                ("human", user_prompt),
            ])
            raw_response = response.content if hasattr(response, "content") else str(response)
            token_usage = self._extract_token_usage(response)
            payload = self._extract_json_payload(raw_response)
            parsed = parser(payload)
            parsed_ok = True
        except Exception as exc:
            error = str(exc)
            parsed = fallback()
            used_fallback = True
        latency_ms = int((time.perf_counter() - started) * 1000)
        trace = MarketMonitorPromptTrace(
            stage=stage,
            card_type=card_type,
            model=self.llm_config.model,
            provider=self.llm_config.provider,
            input_summary=input_summary,
            prompt_text=prompt_text,
            raw_response=raw_response,
            parsed_ok=parsed_ok,
            latency_ms=latency_ms,
            token_usage=token_usage,
            error=error,
        )
        return InferenceResult(payload=parsed, trace=trace, used_fallback=used_fallback)

    @staticmethod
    def _extract_token_usage(response: Any) -> dict[str, int]:
        sources: list[Any] = []
        for attr in ("usage_metadata", "usage"):
            value = getattr(response, attr, None)
            if isinstance(value, dict):
                sources.append(value)
        response_metadata = getattr(response, "response_metadata", None)
        if isinstance(response_metadata, dict):
            for key in ("token_usage", "usage"):
                value = response_metadata.get(key)
                if isinstance(value, dict):
                    sources.append(value)
        for source in sources:
            usage = MarketMonitorInferenceRunner._normalize_token_usage(source)
            if usage:
                return usage
        return {}

    @staticmethod
    def _normalize_token_usage(payload: dict[str, Any]) -> dict[str, int]:
        usage: dict[str, int] = {}
        for key, value in payload.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                usage[key] = value
            elif isinstance(value, float) and value.is_integer():
                usage[key] = int(value)
        return usage

    @staticmethod
    def _extract_json_payload(content: str | None) -> dict[str, Any]:
        if not content:
            raise ValueError("empty response")
        cleaned = content.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL)
        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("response is not a JSON object")
        return payload
