import unittest
from datetime import date, datetime, timezone

import pandas as pd

from tradingagents.web.market_monitor.fact_sheet import build_market_fact_sheet
from tradingagents.web.market_monitor.schemas import MarketMonitorSourceCoverage


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
        coverage = MarketMonitorSourceCoverage(
            completeness="medium",
            available_sources=["ETF/指数日线", "VIX 日线", "本地缓存"],
            missing_sources=["交易所级 breadth"],
            degraded=True,
        )

        fact_sheet = build_market_fact_sheet(
            as_of_date=date(2026, 4, 11),
            generated_at=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
            core_data={"SPY": spy, "QQQ": qqq, "^VIX": pd.DataFrame()},
            local_market_data={"SPY": {"close": 129.0, "above_ma200": True}},
            derived_metrics={"breadth_above_200dma_pct": 63.0, "spy_distance_to_ma200_pct": 4.5},
            source_coverage=coverage,
            open_gaps=["缺少交易所级 breadth 原始数据"],
            notes=["已按代理池与降级规则输出结果。"],
        )

        self.assertEqual(fact_sheet.as_of_date, date(2026, 4, 11))
        self.assertEqual(fact_sheet.derived_metrics["breadth_above_200dma_pct"], 63.0)
        self.assertEqual(fact_sheet.local_facts["symbols"]["SPY"]["latest_close"], 129.0)
        self.assertEqual(fact_sheet.local_facts["market_proxies"]["SPY"]["close"], 129.0)
        self.assertEqual(fact_sheet.open_gaps, ["缺少交易所级 breadth 原始数据"])
        self.assertEqual(fact_sheet.source_coverage.completeness, "medium")
        self.assertGreaterEqual(len(fact_sheet.evidence_refs), 2)
        self.assertEqual(fact_sheet.evidence_refs[0].source_type, "local_market_data")

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
        coverage = MarketMonitorSourceCoverage(
            completeness="medium",
            available_sources=["ETF/指数日线", "VIX 日线", "本地缓存"],
            missing_sources=["交易所级 breadth"],
            degraded=True,
        )

        fact_sheet = build_market_fact_sheet(
            as_of_date=date(2026, 4, 11),
            generated_at=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
            core_data={"SPY": spy},
            local_market_data={"SPY": {"close": 129.0, "above_ma200": True}},
            derived_metrics={},
            source_coverage=coverage,
            open_gaps=[],
            notes=[],
        )

        self.assertEqual(fact_sheet.local_facts["symbols"]["SPY"]["latest_close"], 129.0)
        self.assertEqual(fact_sheet.local_facts["symbols"]["SPY"]["change_5d_pct"], 4.03)
        self.assertEqual(fact_sheet.local_facts["symbols"]["SPY"]["change_20d_pct"], 18.35)


if __name__ == "__main__":
    unittest.main()
