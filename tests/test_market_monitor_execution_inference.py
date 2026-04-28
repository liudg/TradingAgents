import unittest
from unittest.mock import patch

from tests.market_monitor_v231_fixtures import (
    fixture_event_fact,
    fixture_execution_card,
    fixture_fact_sheet,
    fixture_panic_card,
    fixture_score_card,
    fixture_style_effectiveness,
    fixture_system_risk_card,
)
from tradingagents.web.market_monitor.factors import build_execution_card
from tradingagents.web.market_monitor.inference.execution import MarketMonitorExecutionInferenceService
from tradingagents.web.market_monitor.prompts.execution import build_execution_prompt


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLlm:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, messages):
        return _FakeResponse(self._content)


class MarketMonitorExecutionInferenceTests(unittest.TestCase):
    def _build_inputs(self):
        return (
            fixture_fact_sheet(),
            fixture_score_card(),
            fixture_score_card(deterministic_score=61.3, score=61.3, zone="可做区", recommended_exposure=None),
            fixture_system_risk_card(),
            fixture_style_effectiveness(),
            fixture_panic_card(),
            [fixture_event_fact()],
        )

    def test_execution_inference_parses_json(self) -> None:
        content = fixture_execution_card(active_event=True).model_dump_json()
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(content)})(),
        ):
            service = MarketMonitorExecutionInferenceService()
            fact_sheet, long_term, short_term, system_risk, style, panic, event_fact_sheet = self._build_inputs()
            result = service.infer_execution(
                fact_sheet=fact_sheet,
                long_term=long_term,
                short_term=short_term,
                system_risk=system_risk,
                style=style,
                panic=panic,
                event_fact_sheet=event_fact_sheet,
                fallback=lambda: fixture_execution_card(active_event=False),
            )

        self.assertEqual(result.payload.regime_label, "黄绿灯-Swing")
        self.assertFalse(result.used_fallback)
        self.assertEqual(result.trace.stage, "execution_decision")

    def test_execution_inference_preserves_rule_layer_permissions(self) -> None:
        long_term = fixture_score_card(deterministic_score=88.0, score=88.0, zone="强趋势区")
        short_term = fixture_score_card(deterministic_score=82.0, score=82.0, zone="高胜率区", recommended_exposure=None)
        system_risk = fixture_system_risk_card(score=82.0).model_copy(update={"zone": "危机区"})
        style = fixture_style_effectiveness()
        panic = fixture_panic_card()
        fallback = build_execution_card(long_term, short_term, system_risk, style, [], panic)
        llm_payload = fixture_execution_card(active_event=False)
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(llm_payload.model_dump_json())})(),
        ):
            service = MarketMonitorExecutionInferenceService()
            result = service.infer_execution(
                fact_sheet=fixture_fact_sheet(include_event=False),
                long_term=long_term,
                short_term=short_term,
                system_risk=system_risk,
                style=style,
                panic=panic,
                event_fact_sheet=[],
                fallback=lambda: fallback,
            )

        self.assertEqual(result.payload.regime_label, "红灯-危机")
        self.assertFalse(result.payload.new_position_allowed)
        self.assertFalse(result.payload.overnight_allowed)
        self.assertEqual(result.payload.total_exposure_range, "0%-15%")
        self.assertFalse(result.used_fallback)

    def test_execution_prompt_includes_framework_constraints(self) -> None:
        fact_sheet, long_term, short_term, system_risk, style, panic, event_fact_sheet = self._build_inputs()
        system_prompt, user_prompt, input_summary = build_execution_prompt(
            fact_sheet,
            long_term,
            short_term,
            system_risk,
            style,
            panic,
            event_fact_sheet,
        )

        self.assertIn("decision_framework", user_prompt)
        self.assertIn("conflict_matrix", user_prompt)
        self.assertIn("event_risk_rules", user_prompt)
        self.assertIn("signal_confirmation_rules", user_prompt)
        self.assertIn("risk_tightening_rule", user_prompt)
        self.assertIn("risk_loosening_rule", user_prompt)
        self.assertIn("不得重新搜索", system_prompt)
        self.assertEqual(input_summary, "execution decision facts")

    def test_execution_inference_falls_back_when_json_invalid(self) -> None:
        fallback = fixture_execution_card(active_event=False)
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm("not json")})(),
        ):
            service = MarketMonitorExecutionInferenceService()
            fact_sheet, long_term, short_term, system_risk, style, panic, event_fact_sheet = self._build_inputs()
            result = service.infer_execution(
                fact_sheet=fact_sheet,
                long_term=long_term,
                short_term=short_term,
                system_risk=system_risk,
                style=style,
                panic=panic,
                event_fact_sheet=event_fact_sheet,
                fallback=lambda: fallback,
            )

        self.assertTrue(result.used_fallback)
        self.assertEqual(result.payload.regime_label, "黄绿灯-Swing")
        self.assertFalse(result.trace.parsed_ok)


if __name__ == "__main__":
    unittest.main()
