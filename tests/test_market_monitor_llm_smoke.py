import os
import unittest

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.web.market_monitor.inference.base import MarketMonitorInferenceRunner
from tradingagents.web.market_monitor.schemas import MarketMonitorRunLlmConfig


def _default_reasoning_effort(provider: str) -> str | None:
    if provider == "codex":
        return DEFAULT_CONFIG.get("codex_reasoning_effort")
    if provider == "openai":
        return DEFAULT_CONFIG.get("openai_reasoning_effort")
    if provider == "anthropic":
        return DEFAULT_CONFIG.get("anthropic_effort")
    return None


def _parse_smoke_response(payload: dict) -> dict:
    if payload.get("ok") is not True:
        raise ValueError("LLM smoke response must set ok=true")
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("LLM smoke response must include a non-empty message")
    return {"ok": True, "message": message.strip()}


class MarketMonitorLlmSmokeTests(unittest.TestCase):
    @unittest.skipUnless(os.getenv("MARKET_MONITOR_LLM_SMOKE") == "1", "set MARKET_MONITOR_LLM_SMOKE=1 to call the real LLM")
    def test_real_llm_returns_parseable_json(self) -> None:
        provider = os.getenv("MARKET_MONITOR_LLM_PROVIDER") or DEFAULT_CONFIG["llm_provider"]
        model = os.getenv("MARKET_MONITOR_LLM_MODEL") or DEFAULT_CONFIG["deep_think_llm"]
        reasoning_effort = os.getenv("MARKET_MONITOR_LLM_REASONING_EFFORT") or _default_reasoning_effort(provider)
        runner = MarketMonitorInferenceRunner(
            MarketMonitorRunLlmConfig(
                provider=provider,
                model=model,
                reasoning_effort=reasoning_effort,
            )
        )

        result = runner.run_json_inference(
            stage="smoke_test",
            card_type="llm_connectivity",
            system_prompt="Return only valid JSON. Do not include markdown fences or explanatory text.",
            user_prompt='Return exactly this JSON shape with ok true: {"ok": true, "message": "market monitor llm smoke ok"}',
            parser=_parse_smoke_response,
            fallback=lambda: {"ok": False, "message": "fallback"},
            input_summary=f"provider={provider}, model={model}",
        )

        self.assertFalse(result.used_fallback, result.trace.error)
        self.assertTrue(result.trace.parsed_ok, result.trace.raw_response)
        self.assertTrue(result.payload["ok"])
        self.assertTrue(result.trace.raw_response)


if __name__ == "__main__":
    unittest.main()
