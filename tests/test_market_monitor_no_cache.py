import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor_schemas import MarketMonitorModelOverlay, MarketMonitorSnapshotRequest
from tradingagents.web.market_monitor_service import MarketMonitorService
from tradingagents.web.market_monitor_universe import get_market_monitor_universe


def _make_frame(base: float, days: int = 320) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp("2026-04-10"), periods=days, freq="B")
    close = pd.Series([base + i * 0.25 for i in range(days)], index=index)
    return pd.DataFrame(
        {
            "Open": close - 0.25,
            "High": close + 0.75,
            "Low": close - 0.75,
            "Close": close,
            "Volume": pd.Series([500_000 + i * 100 for i in range(days)], index=index),
        }
    )


def _dataset_missing_spy() -> dict[str, dict[str, pd.DataFrame]]:
    universe = get_market_monitor_universe()
    core = {symbol: _make_frame(90 + idx * 2) for idx, symbol in enumerate(universe["core_index_etfs"])}
    core.update({symbol: _make_frame(70 + idx * 2) for idx, symbol in enumerate(universe["sector_etfs"])})
    core["SPY"] = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    core["^VIX"] = _make_frame(22)
    return {"core": core}


class MarketMonitorNoCacheTests(unittest.TestCase):
    def test_missing_required_data_returns_structured_gap_not_placeholder_scores(self) -> None:
        service = MarketMonitorService()
        dataset = _dataset_missing_spy()

        with patch(
            "tradingagents.web.market_monitor_service.build_market_dataset",
            return_value=dataset,
        ), patch.object(
            service._overlay_service,
            "create_overlay",
            return_value=MarketMonitorModelOverlay(status="skipped", notes=["test"]),
        ), patch(
            "tradingagents.web.market_monitor_service.load_snapshot_cache",
            return_value=None,
        ), patch(
            "tradingagents.web.market_monitor_service.save_snapshot_cache",
        ) as mocked_save_cache:
            response = service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertFalse(response.rule_snapshot.ready)
        self.assertIn("SPY", response.rule_snapshot.missing_inputs)
        self.assertIsNone(response.rule_snapshot.long_term_score)
        self.assertEqual(response.rule_snapshot.source_coverage.data_freshness, "live_request_yfinance_daily")
        self.assertNotIn("fallback_placeholder", response.rule_snapshot.source_coverage.data_freshness)
        mocked_save_cache.assert_not_called()


if __name__ == "__main__":
    unittest.main()
