import os
import unittest
from unittest.mock import MagicMock, patch

from tradingagents.web.market_monitor.assessment import MarketMonitorAssessmentService
from tradingagents.web.market_monitor.context import MarketMonitorContextPayload
from tradingagents.web.market_monitor.schemas import MarketDataSnapshot


class MarketMonitorOverlayTests(unittest.TestCase):
    def test_error_assessment_has_safe_execution_defaults(self) -> None:
        service = MarketMonitorAssessmentService()

        assessment = service._build_error_assessment("模型异常")

        self.assertEqual(assessment.execution_card.total_exposure_range, "0%-20%")
        self.assertFalse(assessment.execution_card.new_position_allowed)
        self.assertEqual(assessment.event_risk_card.label, "待确认")
        self.assertEqual(
            assessment.short_term_card.summary,
            "模型返回异常，暂时无法生成短线结论。",
        )

    def test_json_extraction_handles_wrapped_payload(self) -> None:
        service = MarketMonitorAssessmentService()

        payload = service._extract_json_payload("prefix {\"overall_confidence\":0.7} suffix")

        self.assertEqual(payload, {"overall_confidence": 0.7})

    def test_debug_info_truncates_raw_model_output(self) -> None:
        service = MarketMonitorAssessmentService()

        service._record_debug_info(raw_output="x" * 1600, parsed_payload={"assessment": {"foo": "bar"}})

        self.assertEqual(service.last_debug_info["raw_output_preview"], "x" * 1200)
        self.assertEqual(service.last_debug_info["raw_output_length"], 1600)
        self.assertEqual(service.last_debug_info["parsed_top_level_keys"], ["assessment"])

    @patch.dict(os.environ, {"CODEX_API_KEY": "test-key"}, clear=False)
    @patch("tradingagents.web.market_monitor.assessment.OpenAI")
    def test_create_assessment_requests_schema_constrained_json_output(self, mock_openai: MagicMock) -> None:
        service = MarketMonitorAssessmentService()
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.responses.create.return_value = MagicMock(
            output_text=(
                "{\"assessment\": {"
                "\"long_term_card\": {\"label\": \"偏多\", \"summary\": \"测试\", \"confidence\": 0.8, "
                "\"data_completeness\": \"high\", \"key_evidence\": [\"A\"], "
                "\"missing_data_filled_by_search\": [], \"action\": \"持有\"}, "
                "\"short_term_card\": {\"label\": \"中性\", \"summary\": \"测试\", \"confidence\": 0.7, "
                "\"data_completeness\": \"medium\", \"key_evidence\": [\"B\"], "
                "\"missing_data_filled_by_search\": [], \"action\": \"观察\"}, "
                "\"system_risk_card\": {\"label\": \"可控\", \"summary\": \"测试\", \"confidence\": 0.7, "
                "\"data_completeness\": \"medium\", \"key_evidence\": [\"C\"], "
                "\"missing_data_filled_by_search\": [], \"action\": \"控仓\"}, "
                "\"execution_card\": {\"label\": \"谨慎做多\", \"summary\": \"测试\", \"confidence\": 0.75, "
                "\"data_completeness\": \"high\", \"key_evidence\": [\"D\"], "
                "\"missing_data_filled_by_search\": [], \"action\": \"轻仓\", "
                "\"total_exposure_range\": \"30%-50%\", \"new_position_allowed\": true, "
                "\"chase_breakout_allowed\": false, \"dip_buy_allowed\": true, "
                "\"overnight_allowed\": true, \"leverage_allowed\": false, "
                "\"single_position_cap\": \"10%\", \"daily_risk_budget\": \"0.5R\"}, "
                "\"event_risk_card\": {\"label\": \"留意事件\", \"summary\": \"测试\", \"confidence\": 0.6, "
                "\"data_completeness\": \"medium\", \"key_evidence\": [\"E\"], "
                "\"missing_data_filled_by_search\": [], \"action\": \"回避数据日前重仓\"}, "
                "\"panic_card\": {\"label\": \"无恐慌\", \"summary\": \"测试\", \"confidence\": 0.8, "
                "\"data_completeness\": \"high\", \"key_evidence\": [\"F\"], "
                "\"missing_data_filled_by_search\": [], \"action\": \"按计划执行\"}}, "
                "\"evidence_sources\": [\"example.com\"], \"overall_confidence\": 0.8, "
                "\"llm_reasoning_notes\": [\"ok\"]}"
            )
        )
        context = MarketMonitorContextPayload(
            as_of_date="2026-04-12",
            market_data_snapshot=MarketDataSnapshot(
                local_market_data={"SPY": {"close": 100.0}},
                derived_metrics={"vix_close": 20.0},
                llm_reasoning_notes=[],
            ),
            missing_data=[],
            instructions={"goal": "test"},
        )

        assessment, evidence_sources, notes, confidence = service.create_assessment(context)

        self.assertEqual(assessment.long_term_card.data_completeness, "high")
        self.assertEqual(evidence_sources, ["example.com"])
        self.assertEqual(notes, ["ok"])
        self.assertEqual(confidence, 0.8)
        _, kwargs = mock_client.responses.create.call_args
        self.assertIn("data_completeness must be exactly one of: high, medium, low", kwargs["instructions"])
        self.assertIn("must be JSON booleans true or false", kwargs["instructions"])
        self.assertEqual(kwargs["text"]["format"]["type"], "json_schema")


if __name__ == "__main__":
    unittest.main()
