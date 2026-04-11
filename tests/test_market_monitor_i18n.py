import unittest
from datetime import date, timedelta

from pydantic import ValidationError

from tradingagents.web.market_monitor.assessment import MarketMonitorAssessmentService
from tradingagents.web.market_monitor.context import MarketMonitorContextPayload
from tradingagents.web.market_monitor.schemas import (
    MarketDataSnapshot,
    MarketMissingDataItem,
    MarketMonitorSnapshotRequest,
)


class MarketMonitorI18nTests(unittest.TestCase):
    def test_future_as_of_date_uses_chinese_validation_message(self) -> None:
        tomorrow = date.today() + timedelta(days=1)

        with self.assertRaises(ValidationError) as context:
            MarketMonitorSnapshotRequest(as_of_date=tomorrow)

        self.assertIn("as_of_date 不能晚于今天", str(context.exception))

    def test_assessment_parser_returns_chinese_error_when_json_invalid(self) -> None:
        service = MarketMonitorAssessmentService()

        result = service._build_error_assessment("模型返回内容不是合法 JSON。")

        self.assertEqual(result.long_term_card.summary, "模型返回异常，暂时无法生成长线结论。")
        self.assertEqual(result.execution_card.action, "等待下一次刷新或检查模型配置。")

    def test_search_queries_remain_english_for_us_market_context(self) -> None:
        service = MarketMonitorAssessmentService()
        context = MarketMonitorContextPayload(
            as_of_date="2026-04-11",
            market_data_snapshot=MarketDataSnapshot(
                local_market_data={"SPY": {"close": 100.0}},
                derived_metrics={},
                llm_reasoning_notes=[],
            ),
            missing_data=[
                MarketMissingDataItem(
                    key="calendar_events",
                    label="事件日历",
                    required_for=["event_risk_card"],
                    status="missing",
                    note="本地未接入",
                )
            ],
            instructions={"market": "US equities"},
        )

        queries = service._build_search_queries(context)

        self.assertTrue(any("US equities" in query for query in queries))
        self.assertTrue(any("SPY" in query for query in queries))


if __name__ == "__main__":
    unittest.main()
