import unittest
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from tests.market_monitor_v231_fixtures import fixture_event_fact
from tradingagents.web.market_monitor.fact_sheet import build_market_fact_sheet
from tradingagents.web.market_monitor.factors import build_event_fact_sheet, build_input_bundle
from tradingagents.web.market_monitor.universe import get_market_monitor_universe


class MarketMonitorFactSheetTests(unittest.TestCase):
    def test_build_market_fact_sheet_collects_local_facts_metrics_and_evidence(self) -> None:
        index = pd.date_range("2026-04-01", periods=30, freq="B")
        spy = pd.DataFrame(
            {
                "Open": [100 + i for i in range(30)],
                "High": [101 + i for i in range(30)],
                "Low": [99 + i for i in range(30)],
                "Close": [100 + i for i in range(30)],
                "Volume": [1_000_000 + i for i in range(30)],
            },
            index=index,
        )
        qqq = pd.DataFrame(
            {
                "Open": [200 + i for i in range(30)],
                "High": [201 + i for i in range(30)],
                "Low": [199 + i for i in range(30)],
                "Close": [200 + i for i in range(30)],
                "Volume": [2_000_000 + i for i in range(30)],
            },
            index=index,
        )
        event_fact = fixture_event_fact()

        fact_sheet = build_market_fact_sheet(
            as_of_date=date(2026, 4, 11),
            generated_at=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
            core_data={"SPY": spy, "QQQ": qqq, "^VIX": pd.DataFrame()},
            local_market_data={"SPY": {"close": 129.0, "above_ma200": True}},
            derived_metrics={"breadth_above_200dma_pct": 63.0, "spy_distance_to_ma200_pct": 4.5},
            event_fact_sheet=[event_fact],
            open_gaps=["缺少交易所级 breadth 原始数据"],
            notes=["已按代理池与降级规则输出结果。"],
        )

        self.assertEqual(fact_sheet.as_of_date, date(2026, 4, 11))
        self.assertEqual(fact_sheet.derived_metrics["breadth_above_200dma_pct"], 63.0)
        self.assertEqual(fact_sheet.local_facts["symbols"]["SPY"]["latest_close"], 129.0)
        self.assertEqual(fact_sheet.local_facts["market_proxies"]["SPY"]["close"], 129.0)
        self.assertEqual(fact_sheet.open_gaps, ["缺少交易所级 breadth 原始数据"])
        self.assertEqual(fact_sheet.event_fact_sheet[0].event_id, "event-1")
        self.assertGreaterEqual(len(fact_sheet.evidence), 2)
        self.assertEqual(fact_sheet.evidence[0].source_type, "local_market_data")
        self.assertIsInstance(fact_sheet.evidence[0].confidence, float)
        self.assertTrue(any(item.source_type == "event_fact_sheet" for item in fact_sheet.evidence))

    def test_build_event_fact_sheet_normalizes_structured_candidates(self) -> None:
        now = datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)
        bundle = build_input_bundle(
            as_of_date=date(2026, 4, 12),
            dataset={
                "core": {},
                "event_fact_candidates": [
                    {
                        "event": " CPI release ",
                        "scope": "index_level",
                        "time_window": "tomorrow_before_open",
                        "severity": "high",
                        "source_type": "official_calendar",
                        "source_name": "U.S. Bureau of Labor Statistics",
                        "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
                        "source_summary": "CPI 将于次日盘前公布。",
                        "confidence": 1.2,
                        "expires_at": (now + timedelta(days=1)).isoformat(),
                    }
                ],
            },
            universe=get_market_monitor_universe(),
            timestamp=now,
        )

        facts = build_event_fact_sheet(bundle)

        self.assertEqual(len(facts), 1)
        self.assertTrue(facts[0].event_id.startswith("event-"))
        self.assertEqual(facts[0].event, "CPI release")
        self.assertEqual(facts[0].scope, "index_level")
        self.assertEqual(facts[0].severity, "high")
        self.assertEqual(facts[0].confidence, 0.95)

    def test_build_event_fact_sheet_reads_search_candidates(self) -> None:
        now = datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)
        bundle = build_input_bundle(
            as_of_date=date(2026, 4, 12),
            dataset={
                "core": {},
                "search": {
                    "event_fact_candidates": [
                        {
                            "event": "Fed signals rates may stay higher",
                            "scope": "index_level",
                            "severity": "high",
                            "source_type": "news",
                            "source_name": "Reuters",
                            "source_url": "https://example.com/fed-rates",
                            "source_summary": "Policy makers discussed inflation risk.",
                            "observed_at": now.isoformat(),
                            "confidence": 0.78,
                            "expires_at": (now + timedelta(days=1)).isoformat(),
                        }
                    ],
                    "status": {"source": "yfinance_news", "event_fact_candidate_count": 1, "global_news_count": 1, "ticker_news_count": 0, "errors": []},
                },
            },
            universe=get_market_monitor_universe(),
            timestamp=now,
        )

        facts = build_event_fact_sheet(bundle)

        self.assertEqual(len(facts), 1)
        fact = facts[0]
        self.assertTrue(fact.event_id.startswith("event-"))
        self.assertEqual(fact.event, "Fed signals rates may stay higher")
        self.assertEqual(fact.scope, "index_level")
        self.assertEqual(fact.time_window, "next_24h")
        self.assertEqual(fact.severity, "high")
        self.assertEqual(fact.source_name, "Reuters")
        self.assertEqual(fact.source_url, "https://example.com/fed-rates")
        self.assertEqual(fact.confidence, 0.78)

    def test_search_failure_adds_missing_data_without_event_facts(self) -> None:
        now = datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)
        bundle = build_input_bundle(
            as_of_date=date(2026, 4, 12),
            dataset={
                "core": {},
                "search": {
                    "event_fact_candidates": [],
                    "status": {"source": "yfinance_news", "event_fact_candidate_count": 0, "global_news_count": 0, "ticker_news_count": 0, "errors": ["global_news: network down"]},
                },
            },
            universe=get_market_monitor_universe(),
            timestamp=now,
        )

        facts = build_event_fact_sheet(bundle)

        self.assertEqual(facts, [])
        self.assertTrue(any(item.field == "search.event_fact_candidates" for item in bundle.missing_data))
        self.assertTrue(any("联网新闻搜索失败" in item.reason for item in bundle.missing_data))
        self.assertTrue(any("不得编造事件" in item.impact for item in bundle.missing_data))

    def test_history_disabled_news_adds_specific_missing_data(self) -> None:
        now = datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)
        bundle = build_input_bundle(
            as_of_date=date(2026, 4, 12),
            dataset={
                "core": {},
                "search": {
                    "event_fact_candidates": [],
                    "status": {"source": "disabled_for_history", "event_fact_candidate_count": 0, "global_news_count": 0, "ticker_news_count": 0, "errors": []},
                },
            },
            universe=get_market_monitor_universe(),
            timestamp=now,
        )

        self.assertEqual(build_event_fact_sheet(bundle), [])
        self.assertTrue(any("历史回放未注入联网事件事实" in item.reason for item in bundle.missing_data))

    def test_search_articles_without_usable_candidates_adds_specific_missing_data(self) -> None:
        now = datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)
        bundle = build_input_bundle(
            as_of_date=date(2026, 4, 12),
            dataset={
                "core": {},
                "search": {
                    "event_fact_candidates": [],
                    "status": {"source": "yfinance_news", "event_fact_candidate_count": 0, "global_news_count": 1, "ticker_news_count": 0, "errors": []},
                },
            },
            universe=get_market_monitor_universe(),
            timestamp=now,
        )

        self.assertEqual(build_event_fact_sheet(bundle), [])
        self.assertTrue(any("未形成可追溯事件事实" in item.reason for item in bundle.missing_data))

    def test_build_event_fact_sheet_dedupes_and_filters_expired_or_invalid_sources(self) -> None:
        now = datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)
        bundle = build_input_bundle(
            as_of_date=date(2026, 4, 12),
            dataset={
                "core": {},
                "event_fact_candidates": [
                    {
                        "event": "FOMC decision",
                        "scope": "index_level",
                        "time_window": "today_after_close",
                        "severity": "high",
                        "source_type": "news",
                        "source_name": "major news",
                        "source_url": "https://example.com/fomc",
                        "source_summary": "FOMC 决议临近。",
                        "confidence": 0.65,
                        "observed_at": now.isoformat(),
                        "expires_at": (now + timedelta(hours=6)).isoformat(),
                    },
                    {
                        "event": "FOMC decision",
                        "scope": "index_level",
                        "time_window": "today_after_close",
                        "severity": "high",
                        "source_type": "official_calendar",
                        "source_name": "Federal Reserve",
                        "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                        "source_summary": "FOMC 决议临近，可能影响隔夜风险。",
                        "confidence": 0.9,
                        "observed_at": now.isoformat(),
                        "expires_at": (now + timedelta(hours=8)).isoformat(),
                    },
                    {
                        "event": "expired event",
                        "source_type": "news",
                        "source_name": "expired source",
                        "source_summary": "已过期。",
                        "expires_at": (now - timedelta(hours=1)).isoformat(),
                    },
                    {
                        "event": "bad url event",
                        "source_type": "news",
                        "source_name": "bad source",
                        "source_url": "javascript:alert(1)",
                        "source_summary": "URL 不可信。",
                        "expires_at": (now + timedelta(hours=1)).isoformat(),
                    },
                ],
            },
            universe=get_market_monitor_universe(),
            timestamp=now,
        )

        facts = build_event_fact_sheet(bundle)

        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].source_name, "Federal Reserve")
        self.assertEqual(facts[0].confidence, 0.9)

    def test_build_market_fact_sheet_handles_duplicate_close_columns(self) -> None:
        index = pd.date_range("2026-04-01", periods=30, freq="B")
        base = pd.DataFrame(
            {
                "Open": [100 + i for i in range(30)],
                "High": [101 + i for i in range(30)],
                "Low": [99 + i for i in range(30)],
                "Close": [100 + i for i in range(30)],
                "Volume": [1_000_000 + i for i in range(30)],
            },
            index=index,
        )
        spy = pd.concat([base, base[["Close"]]], axis=1)

        fact_sheet = build_market_fact_sheet(
            as_of_date=date(2026, 4, 11),
            generated_at=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
            core_data={"SPY": spy},
            local_market_data={"SPY": {"close": 129.0, "above_ma200": True}},
            derived_metrics={},
            open_gaps=[],
            notes=[],
        )

        self.assertEqual(fact_sheet.local_facts["symbols"]["SPY"]["latest_close"], 129.0)
        self.assertEqual(fact_sheet.local_facts["symbols"]["SPY"]["change_5d_pct"], 4.03)
        self.assertEqual(fact_sheet.local_facts["symbols"]["SPY"]["change_20d_pct"], 18.35)


if __name__ == "__main__":
    unittest.main()
