from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from tradingagents.default_config import DEFAULT_CONFIG
from .schemas import (
    MarketEventRiskFlag,
    MarketEventRiskModifier,
    MarketExecutionAdjustments,
    MarketIndexEventRisk,
    MarketMonitorModelOverlay,
    MarketMonitorRuleSnapshot,
    MarketStockEventRisk,
)


class MarketMonitorLLMService:
    """Build an optional model overlay for market monitor outputs."""

    def __init__(self) -> None:
        self._provider = str(DEFAULT_CONFIG.get("llm_provider", "codex")).strip().lower()
        self._api_key = self._resolve_api_key()
        self._base_url = self._resolve_base_url()
        self._model = str(DEFAULT_CONFIG.get("deep_think_llm", "gpt-5.4"))

    def create_overlay(
        self,
        rule_snapshot: MarketMonitorRuleSnapshot,
        as_of_date: str,
        context_queries: list[str],
    ) -> MarketMonitorModelOverlay:
        if not self._api_key:
            raise RuntimeError(
                f"市场监控模型叠加需要配置 provider '{self._provider}' 对应的 API Key。"
            )
        if not context_queries:
            return MarketMonitorModelOverlay(
                status="skipped",
                notes=["当前快照未生成额外外部上下文问题，已跳过模型叠加。"],
            )

        client_kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url
        client = OpenAI(**client_kwargs)
        prompt_payload = {
            "as_of_date": as_of_date,
            "rule_snapshot": rule_snapshot.model_dump(mode="json"),
            "questions": context_queries,
            "allowed_changes": {
                "regime_override": True,
                "execution_adjustments": [
                    "regime_label",
                    "conflict_mode",
                    "new_position_allowed",
                    "chase_breakout_allowed",
                    "dip_buy_allowed",
                    "overnight_allowed",
                    "daily_risk_budget",
                    "summary",
                ],
                "event_risk_override": True,
                "panic_narrative": True,
            },
            "forbidden_changes": [
                "long_term_score",
                "short_term_score",
                "system_risk_score",
                "style_effectiveness",
                "panic_reversal_score.numeric_fields",
                "key_indicators",
            ],
        }
        instructions = (
            "你正在协助一个确定性的市场监控引擎。"
            "只允许使用 web search 收集宏观事件、市场新闻、财报/日历事件，以及解释数据降级原因的外部信息。"
            "不得编造或覆盖价格、指标、广度、分数或风格因子。"
            "只有在外部证据足够充分时，才可以选择性调整 regime/action/event risk。"
            "必须只返回严格 JSON，且仅包含这些 key："
            "regime_override, execution_adjustments, event_risk_override, "
            "market_narrative, risk_narrative, panic_narrative, evidence_sources, model_confidence, notes。"
            "未使用的 override 请返回 null；evidence_sources 必须是简短 URL 或域名。"
        )

        try:
            response = client.responses.create(
                model=self._model,
                instructions=instructions,
                input=json.dumps(prompt_payload, ensure_ascii=True),
                reasoning={"effort": "low"},
                max_output_tokens=1200,
                tools=[
                    {
                        "type": "web_search",
                        "search_context_size": "medium",
                        "user_location": {
                            "type": "approximate",
                            "country": "US",
                            "region": "California",
                            "timezone": "America/Los_Angeles",
                        },
                    }
                ],
            )
        except Exception as exc:
            return MarketMonitorModelOverlay(
                status="error",
                notes=[f"OpenAI web_search 请求失败：{exc}"],
            )

        content = getattr(response, "output_text", "") or ""
        payload = self._extract_json_payload(content)
        if payload is None:
            return MarketMonitorModelOverlay(
                status="error",
                notes=["OpenAI web_search 返回内容不是合法 JSON。"],
            )

        try:
            overlay = MarketMonitorModelOverlay(
                status="applied",
                regime_override=payload.get("regime_override"),
                execution_adjustments=(
                    MarketExecutionAdjustments.model_validate(payload["execution_adjustments"])
                    if payload.get("execution_adjustments")
                    else None
                ),
                event_risk_override=self._parse_event_risk(payload.get("event_risk_override")),
                market_narrative=str(payload.get("market_narrative") or ""),
                risk_narrative=str(payload.get("risk_narrative") or ""),
                panic_narrative=str(payload.get("panic_narrative") or ""),
                evidence_sources=[str(item) for item in payload.get("evidence_sources", [])][:8],
                model_confidence=payload.get("model_confidence"),
                notes=[str(item) for item in payload.get("notes", [])][:8],
            )
        except Exception as exc:
            return MarketMonitorModelOverlay(
                status="error",
                notes=[f"模型叠加结果校验失败：{exc}"],
            )
        return overlay

    def _resolve_api_key(self) -> str:
        if self._provider == "codex":
            return os.getenv("CODEX_API_KEY", "").strip()
        return os.getenv("OPENAI_API_KEY", "").strip()

    def _resolve_base_url(self) -> str | None:
        if self._provider == "codex":
            return str(DEFAULT_CONFIG.get("backend_url") or "").strip() or None
        return None

    def _extract_json_payload(self, content: str) -> dict[str, Any] | None:
        if not content:
            return None
        stripped = content.strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None

    def _parse_event_risk(self, payload: Any) -> MarketEventRiskFlag | None:
        if not payload:
            return None
        try:
            return MarketEventRiskFlag.model_validate(payload)
        except Exception:
            pass
        if isinstance(payload, dict):
            return MarketEventRiskFlag(
                index_level=MarketIndexEventRisk.model_validate(
                    self._normalize_index_event_risk(payload.get("index_level", {}))
                ),
                stock_level=MarketStockEventRisk.model_validate(payload.get("stock_level", {})),
            )
        return None

    def _normalize_index_event_risk(self, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return payload

        normalized = dict(payload)
        action_modifier = normalized.get("action_modifier")
        if isinstance(action_modifier, str):
            normalized["action_modifier"] = MarketEventRiskModifier(note=action_modifier).model_dump(
                mode="python"
            )
        return normalized
