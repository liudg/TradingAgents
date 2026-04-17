import unittest
from datetime import date
from typing import Any
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.data import _expected_market_close_date
from tradingagents.web.market_monitor.metrics import build_market_snapshot
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorHistoryRequest,
    MarketMonitorSnapshotRequest,
)
from tradingagents.web.market_monitor.snapshot_service import MarketMonitorSnapshotService
from tradingagents.web.market_monitor.universe import get_market_monitor_universe


def _make_frame(base: float, days: int = 320) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp("2026-04-10"), periods=days, freq="B")
    close = pd.Series([base + i * 0.4 for i in range(days)], index=index)
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": pd.Series([1_000_000 + i * 100 for i in range(days)], index=index),
        }
    )


def _complete_dataset() -> dict[str, Any]:
    universe = get_market_monitor_universe()
    core = {symbol: _make_frame(100 + idx * 3) for idx, symbol in enumerate(universe["core_index_etfs"])}
    core.update({symbol: _make_frame(80 + idx * 2) for idx, symbol in enumerate(universe["sector_etfs"])})
    core["^VIX"] = _make_frame(18, days=320)
    return {
        "core": core,
        "cache_summary": {
            "counts": {
                "cache_missing": 1,
                "cache_corrupted": 1,
                "cache_invalid_structure": 1,
                "cache_stale": 1,
                "cache_hit": 8,
            },
            "result_counts": {
                "cache_hit": 8,
                "refreshed": 3,
                "stale_fallback": 1,
                "empty": 0,
            },
            "symbols": [
                {
                    "symbol": "SPY",
                    "cache_state": "cache_hit",
                    "result_state": "cache_hit",
                    "rows": 320,
                    "expected_close_date": "2026-04-10",
                    "cache_end_date": "2026-04-10",
                    "last_successful_refresh_at": "2026-04-10T00:00:00+00:00",
                    "reason": None,
                },
                {
                    "symbol": "QQQ",
                    "cache_state": "cache_missing",
                    "result_state": "refreshed",
                    "rows": 320,
                    "expected_close_date": "2026-04-10",
                    "cache_end_date": "2026-04-10",
                    "last_successful_refresh_at": "2026-04-10T00:00:00+00:00",
                    "reason": None,
                },
            ],
        },
    }


class MarketMonitorRulesTests(unittest.TestCase):
    def test_symbol_cache_requires_requested_trading_day(self) -> None:
        self.assertEqual(_expected_market_close_date(date(2026, 4, 12)), pd.Timestamp("2026-04-10"))
        self.assertEqual(_expected_market_close_date(date(2026, 4, 3)), pd.Timestamp("2026-04-02"))

    def test_metrics_builder_returns_local_data_and_derived_metrics(self) -> None:
        dataset = _complete_dataset()
        universe = get_market_monitor_universe()

        local_market_data, derived_metrics = build_market_snapshot(
            dataset["core"], universe["market_proxies"]
        )

        self.assertIn("SPY", local_market_data)
        self.assertIn("breadth_above_200dma_pct", derived_metrics)
        self.assertIn("spy_range_position_3m_pct", derived_metrics)

    def test_snapshot_service_builds_formal_snapshot(self) -> None:
        dataset = _complete_dataset()
        service = MarketMonitorSnapshotService()

        with patch(
            "tradingagents.web.market_monitor.snapshot_service.build_market_dataset",
            return_value=dataset,
        ):
            snapshot = service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertEqual(snapshot.as_of_date, date(2026, 4, 10))
        self.assertTrue(snapshot.execution_card.regime_label)
        self.assertTrue(snapshot.execution_card.summary)
        self.assertEqual(snapshot.execution_card.signal_confirmation.current_regime_days, 1)
        self.assertIn("ETF/指数日线", snapshot.source_coverage.available_sources)
        self.assertIn("交易所级 breadth", snapshot.source_coverage.missing_sources)
        self.assertIn("广度因子使用 ETF 代理池近似", snapshot.degraded_factors)
        self.assertTrue(len(snapshot.notes) > 0)
        self.assertGreaterEqual(snapshot.long_term_score.score, 0)
        self.assertLessEqual(snapshot.long_term_score.score, 100)
        self.assertGreaterEqual(snapshot.short_term_score.score, 0)
        self.assertLessEqual(snapshot.short_term_score.score, 100)
        self.assertGreaterEqual(snapshot.system_risk_score.score, 0)
        self.assertLessEqual(snapshot.system_risk_score.score, 100)
        self.assertGreaterEqual(snapshot.panic_reversal_score.score, 0)
        self.assertLessEqual(snapshot.panic_reversal_score.score, 100)

    def test_snapshot_service_data_status_uses_open_gaps(self) -> None:
        dataset = _complete_dataset()
        service = MarketMonitorSnapshotService()

        with patch(
            "tradingagents.web.market_monitor.snapshot_service.build_market_dataset",
            return_value=dataset,
        ):
            data_status = service.get_data_status(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertEqual(data_status.as_of_date, date(2026, 4, 10))
        self.assertIn("缺少交易所级 breadth 原始数据", data_status.open_gaps)
        self.assertIn("广度因子使用 ETF 代理池近似", data_status.degraded_factors)
        self.assertTrue(data_status.source_coverage.degraded)

    def test_snapshot_service_history_returns_requested_days(self) -> None:
        dataset = _complete_dataset()
        service = MarketMonitorSnapshotService()

        with patch(
            "tradingagents.web.market_monitor.snapshot_service.build_market_dataset",
            return_value=dataset,
        ):
            history = service.get_history(
                MarketMonitorHistoryRequest(as_of_date=date(2026, 4, 10), days=3)
            )

        self.assertEqual(history.as_of_date, date(2026, 4, 10))
        self.assertEqual(len(history.points), 3)
        self.assertEqual(sorted(point.trade_date for point in history.points), [point.trade_date for point in history.points])
        self.assertTrue(all(point.regime_label for point in history.points))

    def test_snapshot_service_history_skips_holidays(self) -> None:
        dataset = _complete_dataset()
        service = MarketMonitorSnapshotService()

        with patch(
            "tradingagents.web.market_monitor.snapshot_service.build_market_dataset",
            return_value=dataset,
        ) as build_dataset_mock:
            history = service.get_history(
                MarketMonitorHistoryRequest(as_of_date=date(2026, 4, 3), days=2)
            )

        self.assertEqual(history.as_of_date, date(2026, 4, 3))
        self.assertEqual([point.trade_date for point in history.points], [date(2026, 4, 1), date(2026, 4, 2)])
        self.assertEqual(
            [call.args[1] for call in build_dataset_mock.call_args_list],
            [date(2026, 4, 2), date(2026, 4, 1)],
        )

    def test_snapshot_service_event_risk_weekday_rules(self) -> None:
        service = MarketMonitorSnapshotService()

        monday = service._build_event_risk(date(2026, 4, 13))
        friday = service._build_event_risk(date(2026, 4, 17))

        self.assertEqual(monday.stock_level.earnings_stocks, ["NVDA", "META"])
        self.assertIsNotNone(monday.stock_level.rule)
        self.assertFalse(friday.index_level.active)
        self.assertEqual(friday.stock_level.earnings_stocks, [])

    def test_snapshot_service_open_gaps_include_missing_core_series(self) -> None:
        service = MarketMonitorSnapshotService()
        gaps = service._build_open_gaps({"SPY": pd.DataFrame()})

        self.assertIn("缺少 QQQ 日线", gaps)
        self.assertIn("缺少 IWM 日线", gaps)
        self.assertIn("缺少 ^VIX 日线", gaps)
        self.assertIn("缺少未来三日宏观与财报事件原始日历", gaps)


if __name__ == "__main__":
    unittest.main()
