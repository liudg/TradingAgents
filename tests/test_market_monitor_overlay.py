import unittest

from tradingagents.web.market_monitor.assessment import MarketMonitorAssessmentService


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


if __name__ == "__main__":
    unittest.main()
