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


class MarketMonitorInferenceRunner:
    def __init__(self, llm_config: MarketMonitorRunLlmConfig | None = None) -> None:
        config = llm_config or MarketMonitorRunLlmConfig(
            provider=DEFAULT_CONFIG["llm_provider"],
            model=DEFAULT_CONFIG["quick_think_llm"],
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
            model=config.model or DEFAULT_CONFIG["quick_think_llm"],
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
        try:
            response = self.llm.invoke([
                ("system", system_prompt),
                ("human", user_prompt),
            ])
            raw_response = response.content if hasattr(response, "content") else str(response)
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
            error=error,
        )
        return InferenceResult(payload=parsed, trace=trace, used_fallback=used_fallback)

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
