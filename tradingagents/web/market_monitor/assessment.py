from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from tradingagents.default_config import DEFAULT_CONFIG
from .context import MarketMonitorContextPayload
from .schemas import MarketAssessment, MarketAssessmentCard, MarketAssessmentExecutionCard


class MarketMonitorAssessmentService:
    def __init__(self) -> None:
        self._provider = str(DEFAULT_CONFIG.get("llm_provider", "codex")).strip().lower()
        self._api_key = self._resolve_api_key()
        self._base_url = self._resolve_base_url()
        self._model = str(DEFAULT_CONFIG.get("deep_think_llm", "gpt-5.4"))
        self._last_debug_info: dict[str, Any] = {}

    def create_assessment(
        self,
        context: MarketMonitorContextPayload,
    ) -> tuple[MarketAssessment, list[str], list[str], float]:
        self._last_debug_info = {}
        if not self._api_key:
            self._record_debug_info(error="missing_api_key")
            return (
                self._build_error_assessment(f"缺少 {self._provider} 对应的 API Key。"),
                [],
                ["模型配置缺失，已返回降级结论。"],
                0.15,
            )

        client_kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            client_kwargs["base_url"] = self._base_url
        client = OpenAI(**client_kwargs)

        instructions = (
            "你是一个美国股市市场监控裁决器。"
            "必须优先使用提供的本地结构化市场数据。"
            "对于缺失但重要的数据，必须先用 web search 搜索补充，再给出结论。"
            "输出必须是严格 JSON，且只包含 keys: assessment, evidence_sources, overall_confidence, llm_reasoning_notes。"
            "assessment 下必须包含 long_term_card, short_term_card, system_risk_card, execution_card, event_risk_card, panic_card。"
            "每张卡都必须包含 label, summary, confidence, data_completeness, key_evidence, missing_data_filled_by_search, action。"
            "execution_card 还必须包含 total_exposure_range, new_position_allowed, chase_breakout_allowed, dip_buy_allowed, overnight_allowed, leverage_allowed, single_position_cap, daily_risk_budget。"
            "data_completeness must be exactly one of: high, medium, low."
            "All *_allowed fields must be JSON booleans true or false, never strings, never Chinese text, never explanations."
            "confidence 和 overall_confidence 必须是 0 到 1 之间的数字。"
            "missing_data_filled_by_search、key_evidence、evidence_sources、llm_reasoning_notes 必须是字符串数组。"
            "如果信息不足，降低 confidence 并在 summary/action 中明确不确定性。"
        )

        try:
            response = client.responses.create(
                model=self._model,
                instructions=instructions,
                input=context.model_dump_json(),
                reasoning={"effort": "low"},
                max_output_tokens=2200,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "market_monitor_assessment",
                        "strict": True,
                        "schema": self._response_json_schema(),
                    }
                },
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
            self._record_debug_info(error=f"request_failed: {exc}")
            return (
                self._build_error_assessment(f"搜索或模型请求失败：{exc}"),
                [],
                [f"搜索或模型请求失败：{exc}"],
                0.12,
            )

        raw_output = getattr(response, "output_text", "") or ""
        payload = self._extract_json_payload(raw_output)
        self._record_debug_info(raw_output=raw_output, parsed_payload=payload)
        if payload is None:
            return (
                self._build_error_assessment("模型返回内容不是合法 JSON。"),
                [],
                ["模型返回内容不是合法 JSON。"],
                0.1,
            )

        try:
            assessment = MarketAssessment.model_validate(payload.get("assessment"))
            evidence_sources = [str(item) for item in payload.get("evidence_sources", [])][:12]
            notes = [str(item) for item in payload.get("llm_reasoning_notes", [])][:12]
            overall_confidence = float(payload.get("overall_confidence", 0.5))
            overall_confidence = max(0.0, min(1.0, overall_confidence))
            return assessment, evidence_sources, notes, overall_confidence
        except Exception as exc:
            self._record_debug_info(raw_output=raw_output, parsed_payload=payload, error=f"validation_failed: {exc}")
            return (
                self._build_error_assessment(f"模型输出结构校验失败：{exc}"),
                [],
                [f"模型输出结构校验失败：{exc}"],
                0.1,
            )

    @property
    def last_debug_info(self) -> dict[str, Any]:
        return dict(self._last_debug_info)

    def _build_search_queries(self, context: MarketMonitorContextPayload) -> list[str]:
        queries = [
            f"What macro events are most relevant to US equities around {context.as_of_date}?",
            "What major earnings, policy, geopolitical, or regulatory catalysts affect SPY, QQQ, IWM, or mega-cap tech in the next 3 trading days?",
        ]
        if context.missing_data:
            queries.append(
                "What missing market context should be considered for US equities when breadth, event calendars, or volatility term structure data are unavailable locally?"
            )
        return queries

    def _resolve_api_key(self) -> str:
        if self._provider == "codex":
            return os.getenv("CODEX_API_KEY", "").strip()
        return os.getenv("OPENAI_API_KEY", "").strip()

    def _resolve_base_url(self) -> str | None:
        if self._provider == "codex":
            return str(DEFAULT_CONFIG.get("backend_url") or "").strip() or None
        return None

    def _response_json_schema(self) -> dict[str, Any]:
        card_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "label",
                "summary",
                "confidence",
                "data_completeness",
                "key_evidence",
                "missing_data_filled_by_search",
                "action",
            ],
            "properties": {
                "label": {"type": "string"},
                "summary": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "data_completeness": {"type": "string", "enum": ["high", "medium", "low"]},
                "key_evidence": {"type": "array", "items": {"type": "string"}},
                "missing_data_filled_by_search": {"type": "array", "items": {"type": "string"}},
                "action": {"type": "string"},
            },
        }
        execution_card_schema = {
            **card_schema,
            "required": [
                *card_schema["required"],
                "total_exposure_range",
                "new_position_allowed",
                "chase_breakout_allowed",
                "dip_buy_allowed",
                "overnight_allowed",
                "leverage_allowed",
                "single_position_cap",
                "daily_risk_budget",
            ],
            "properties": {
                **card_schema["properties"],
                "total_exposure_range": {"type": "string"},
                "new_position_allowed": {"type": "boolean"},
                "chase_breakout_allowed": {"type": "boolean"},
                "dip_buy_allowed": {"type": "boolean"},
                "overnight_allowed": {"type": "boolean"},
                "leverage_allowed": {"type": "boolean"},
                "single_position_cap": {"type": "string"},
                "daily_risk_budget": {"type": "string"},
            },
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["assessment", "evidence_sources", "overall_confidence", "llm_reasoning_notes"],
            "properties": {
                "assessment": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "long_term_card",
                        "short_term_card",
                        "system_risk_card",
                        "execution_card",
                        "event_risk_card",
                        "panic_card",
                    ],
                    "properties": {
                        "long_term_card": card_schema,
                        "short_term_card": card_schema,
                        "system_risk_card": card_schema,
                        "execution_card": execution_card_schema,
                        "event_risk_card": card_schema,
                        "panic_card": card_schema,
                    },
                },
                "evidence_sources": {"type": "array", "items": {"type": "string"}},
                "overall_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "llm_reasoning_notes": {"type": "array", "items": {"type": "string"}},
            },
        }

    def _record_debug_info(
        self,
        raw_output: str | None = None,
        parsed_payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        preview = (raw_output or "")[:1200]
        self._last_debug_info = {
            "raw_output_preview": preview,
            "raw_output_length": len(raw_output or ""),
            "parsed_payload_present": parsed_payload is not None,
            "parsed_top_level_keys": sorted(parsed_payload.keys()) if isinstance(parsed_payload, dict) else [],
        }
        if error:
            self._last_debug_info["error"] = error

    def _extract_json_payload(self, content: str) -> dict[str, Any] | None:
        stripped = content.strip()
        if not stripped:
            return None
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

    def _build_error_assessment(self, reason: str) -> MarketAssessment:
        fallback_payload = {
            "label": "待确认",
            "summary": "模型返回异常，暂时无法生成长线结论。",
            "confidence": 0.1,
            "data_completeness": "low",
            "key_evidence": [reason],
            "missing_data_filled_by_search": [],
            "action": "等待下一次刷新或检查模型配置。",
        }
        fallback = MarketAssessmentCard(**fallback_payload)
        return MarketAssessment(
            long_term_card=fallback,
            short_term_card=MarketAssessmentCard.model_validate(
                {**fallback.model_dump(mode="python"), "summary": "模型返回异常，暂时无法生成短线结论。"}
            ),
            system_risk_card=MarketAssessmentCard.model_validate(
                {**fallback.model_dump(mode="python"), "summary": "模型返回异常，暂时无法生成系统风险结论。"}
            ),
            event_risk_card=MarketAssessmentCard.model_validate(
                {**fallback.model_dump(mode="python"), "summary": "模型返回异常，暂时无法生成事件风险结论。"}
            ),
            panic_card=MarketAssessmentCard.model_validate(
                {**fallback.model_dump(mode="python"), "summary": "模型返回异常，暂时无法生成恐慌模块结论。"}
            ),
            execution_card=MarketAssessmentExecutionCard(
                **{**fallback_payload, "summary": "模型返回异常，暂时无法生成执行建议。"},
                total_exposure_range="0%-20%",
                new_position_allowed=False,
                chase_breakout_allowed=False,
                dip_buy_allowed=False,
                overnight_allowed=False,
                leverage_allowed=False,
                single_position_cap="5%",
                daily_risk_budget="0.25R",
            ),
        )
