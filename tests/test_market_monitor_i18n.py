import unittest
from datetime import date, timedelta

from pydantic import ValidationError

from tradingagents.web.market_monitor.llm import MarketMonitorLLMService
from tradingagents.web.market_monitor.schemas import MarketMonitorSnapshotRequest
from tradingagents.web.market_monitor.service import MarketMonitorService


class MarketMonitorI18nTests(unittest.TestCase):
    def test_future_as_of_date_uses_chinese_validation_message(self) -> None:
        tomorrow = date.today() + timedelta(days=1)

        with self.assertRaises(ValidationError) as context:
            MarketMonitorSnapshotRequest(as_of_date=tomorrow)

        self.assertIn("as_of_date 不能晚于今天", str(context.exception))

    def test_overlay_without_context_returns_chinese_note(self) -> None:
        service = MarketMonitorLLMService()
        service._api_key = "test-key"

        overlay = service.create_overlay(
            rule_snapshot=None,  # type: ignore[arg-type]
            as_of_date="2026-04-11",
            context_queries=[],
        )

        self.assertEqual(overlay.status, "skipped")
        self.assertEqual(overlay.notes, ["当前快照未生成额外外部上下文问题，已跳过模型叠加。"])

    def test_context_queries_remain_english_for_us_market_search(self) -> None:
        service = MarketMonitorService()
        rule_snapshot = type(
            "RuleSnapshotStub",
            (),
            {
                "degraded_factors": ["calendar_events_missing"],
                "base_regime_label": "red",
            },
        )()

        queries = service._build_context_queries(rule_snapshot)

        self.assertTrue(any("US equities" in query for query in queries))
        self.assertTrue(any("SPY, QQQ, IWM" in query for query in queries))
        self.assertTrue(any("risk-off" in query or "defensive" in query for query in queries))


if __name__ == "__main__":
    unittest.main()
