import json
import unittest
from typing import Any

from tests.market_monitor_v231_fixtures import (
    fixture_event_risk_flag,
    fixture_fact_sheet,
    fixture_panic_card,
    fixture_score_card,
    fixture_style_effectiveness,
    fixture_system_risk_card,
)
from tradingagents.web.market_monitor.inference.cards import MarketMonitorCardInferenceService
from tradingagents.web.market_monitor.schemas import MarketMonitorScoreAdjustment
from unittest.mock import patch


class _FakeResponse:
    def __init__(self, content: str, **kwargs: Any) -> None:
        self.content = content
        for key, value in kwargs.items():
            setattr(self, key, value)


class _FakeLlm:
    def __init__(self, content: str, **response_kwargs: Any) -> None:
        self._content = content
        self._response_kwargs = response_kwargs

    def invoke(self, messages):
        return _FakeResponse(self._content, **self._response_kwargs)


class MarketMonitorInferenceTests(unittest.TestCase):
    def test_long_term_inference_enforces_deterministic_score_and_clamps_adjustment(self) -> None:
        deterministic = fixture_score_card(deterministic_score=67.5, score=67.5)
        llm_payload = deterministic.model_copy(
            update={
                "score": 92.0,
                "score_reasoning": "趋势与广度同时改善。",
                "score_adjustment": MarketMonitorScoreAdjustment(
                    value=12.0,
                    direction="up",
                    reason="事件事实支持小幅上调。",
                    source_event_ids=["event-1"],
                    confidence=0.7,
                ),
            }
        )
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(llm_payload.model_dump_json())})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_long_term(
                fixture_fact_sheet(),
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertEqual(result.payload.score, 72.5)
        self.assertEqual(result.payload.deterministic_score, 67.5)
        self.assertEqual(result.payload.factor_breakdown, deterministic.factor_breakdown)
        self.assertEqual(result.payload.score_adjustment.value, 5.0)
        self.assertFalse(result.used_fallback)
        self.assertTrue(result.trace.parsed_ok)
        self.assertEqual(result.trace.card_type, "long_term")

    def test_trace_records_supported_token_usage_metadata(self) -> None:
        deterministic = fixture_score_card(deterministic_score=67.5, score=67.5)
        content = deterministic.model_copy(update={"score_reasoning": "保留确定性结构，仅补充解释。"}).model_dump_json()
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type(
                "_FakeClient",
                (),
                {
                    "get_llm": lambda self: _FakeLlm(
                        content,
                        usage_metadata={"input_tokens": 120, "output_tokens": 35, "total_tokens": 155},
                    )
                },
            )(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_long_term(
                fixture_fact_sheet(),
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertTrue(result.trace.parsed_ok)
        self.assertEqual(
            result.trace.token_usage,
            {"input_tokens": 120, "output_tokens": 35, "total_tokens": 155},
        )

    def test_trace_records_response_metadata_token_usage(self) -> None:
        deterministic = fixture_score_card(deterministic_score=67.5, score=67.5)
        content = deterministic.model_dump_json()
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type(
                "_FakeClient",
                (),
                {
                    "get_llm": lambda self: _FakeLlm(
                        content,
                        response_metadata={"token_usage": {"prompt_tokens": 90, "completion_tokens": 20, "total_tokens": 110}},
                    )
                },
            )(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_long_term(
                fixture_fact_sheet(),
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertFalse(result.used_fallback)
        self.assertEqual(result.trace.token_usage["prompt_tokens"], 90)
        self.assertEqual(result.trace.token_usage["completion_tokens"], 20)

    def test_trace_keeps_empty_token_usage_when_not_supported(self) -> None:
        deterministic = fixture_score_card(deterministic_score=67.5, score=67.5)
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(deterministic.model_dump_json())})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_long_term(
                fixture_fact_sheet(),
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertFalse(result.used_fallback)
        self.assertEqual(result.trace.token_usage, {})

    def test_score_adjustment_accepts_adjustment_alias_and_derives_direction(self) -> None:
        deterministic = fixture_score_card(deterministic_score=67.5, score=67.5)
        payload = deterministic.model_dump(mode="json") | {
            "score_adjustment": {
                "adjustment": -2.0,
                "reason": "事件事实支持下调风险偏好。",
                "source_event_ids": ["event-1"],
                "confidence": 0.68,
            }
        }
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(json.dumps(payload, ensure_ascii=False))})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_long_term(
                fixture_fact_sheet(),
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertFalse(result.used_fallback)
        self.assertTrue(result.trace.parsed_ok)
        self.assertEqual(result.payload.score, 65.5)
        self.assertEqual(result.payload.score_adjustment.value, -2.0)
        self.assertEqual(result.payload.score_adjustment.direction, "down")

    def test_score_adjustment_is_dropped_without_valid_event_reference(self) -> None:
        deterministic = fixture_score_card(deterministic_score=67.5, score=67.5)
        for source_event_ids in ([], ["unknown-event"]):
            llm_payload = deterministic.model_copy(
                update={
                    "score": 72.0,
                    "score_adjustment": MarketMonitorScoreAdjustment(
                        value=4.0,
                        direction="up",
                        reason="缺少有效事件引用。",
                        source_event_ids=source_event_ids,
                        confidence=0.7,
                    ),
                }
            )
            with patch(
                "tradingagents.web.market_monitor.inference.base.create_llm_client",
                return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(llm_payload.model_dump_json())})(),
            ):
                service = MarketMonitorCardInferenceService()
                result = service.infer_long_term(
                    fixture_fact_sheet(),
                    deterministic,
                    fallback=lambda: deterministic,
                )

            self.assertEqual(result.payload.score, 67.5)
            self.assertIsNone(result.payload.score_adjustment)

    def test_score_adjustment_expiry_is_capped_to_source_event(self) -> None:
        deterministic = fixture_score_card(deterministic_score=67.5, score=67.5)
        fact_sheet = fixture_fact_sheet()
        llm_payload = deterministic.model_copy(
            update={
                "score_adjustment": MarketMonitorScoreAdjustment(
                    value=3.0,
                    direction="up",
                    reason="有效事件支持小幅上调。",
                    source_event_ids=["event-1"],
                    confidence=0.7,
                    expires_at=fact_sheet.event_fact_sheet[0].expires_at.replace(year=2027),
                ),
            }
        )
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(llm_payload.model_dump_json())})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_long_term(
                fact_sheet,
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertEqual(result.payload.score, 70.5)
        self.assertEqual(result.payload.score_adjustment.expires_at, fact_sheet.event_fact_sheet[0].expires_at)

    def test_system_risk_inference_falls_back_when_json_invalid(self) -> None:
        deterministic = fixture_system_risk_card()
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm("not json")})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_system_risk(
                fixture_fact_sheet(),
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertTrue(result.used_fallback)
        self.assertFalse(result.trace.parsed_ok)
        self.assertEqual(result.payload.zone, "正常区")
        self.assertIsNotNone(result.trace.error)

    def test_event_risk_inference_parses_nested_json(self) -> None:
        deterministic = fixture_event_risk_flag(active=False)
        content = fixture_event_risk_flag(active=True).model_dump_json()
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(content)})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_event_risk(
                fixture_fact_sheet(),
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertTrue(result.payload.index_level.active)
        self.assertEqual(result.payload.index_level.events, ["宏观数据窗口"])
        self.assertEqual(result.payload.stock_level.earnings_stocks, ["NVDA"])

    def test_short_term_inference_parses_json(self) -> None:
        deterministic = fixture_score_card(deterministic_score=61.3, score=61.3, zone="可做区", recommended_exposure=None)
        content = deterministic.model_copy(update={"score_reasoning": "行业动量扩散改善，波动尚可承受。"}).model_dump_json()
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(content)})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_short_term(
                fixture_fact_sheet(),
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertFalse(result.used_fallback)
        self.assertEqual(result.payload.zone, "可做区")
        self.assertEqual(result.trace.card_type, "short_term")

    def test_style_inference_preserves_deterministic_layers(self) -> None:
        deterministic = fixture_style_effectiveness()
        llm_payload = deterministic.model_copy(
            update={
                "tactic_layer": deterministic.tactic_layer.model_copy(update={"top_tactic": "趋势突破"}),
                "asset_layer": deterministic.asset_layer.model_copy(update={"preferred_assets": ["大盘科技"]}),
                "score_reasoning": "LLM 只能解释风格，不能改写规则层。",
            }
        )
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(llm_payload.model_dump_json())})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_style(
                fixture_fact_sheet(),
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertEqual(result.payload.tactic_layer.top_tactic, "回调低吸")
        self.assertEqual(result.payload.asset_layer.preferred_assets, ["防御板块", "能源/周期"])
        self.assertEqual(result.payload.score_reasoning, "LLM 只能解释风格，不能改写规则层。")
        self.assertEqual(result.trace.card_type, "style")

    def test_style_inference_accepts_object_risks(self) -> None:
        deterministic = fixture_style_effectiveness()
        payload = deterministic.model_dump(mode="json") | {
            "risks": [
                {"risk": "指数处于高位，突破策略容易承受回撤。", "evidence": ["SPY 20d=9.42%"]},
                {"risk": "AI/半导体相关事件可能放大成长风格波动。"},
            ]
        }
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(json.dumps(payload, ensure_ascii=False))})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_style(
                fixture_fact_sheet(),
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertFalse(result.used_fallback)
        self.assertTrue(result.trace.parsed_ok)
        self.assertEqual(
            result.payload.risks,
            [
                "指数处于高位，突破策略容易承受回撤。",
                "AI/半导体相关事件可能放大成长风格波动。",
            ],
        )

    def test_panic_inference_falls_back_when_json_invalid(self) -> None:
        deterministic = fixture_panic_card()
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm("invalid")})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_panic(
                fixture_fact_sheet(),
                deterministic,
                fallback=lambda: deterministic,
            )

        self.assertTrue(result.used_fallback)
        self.assertEqual(result.payload.state, "panic_watch")
        self.assertFalse(result.trace.parsed_ok)
        self.assertEqual(result.trace.card_type, "panic")


if __name__ == "__main__":
    unittest.main()
