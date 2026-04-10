import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.schemas import MarketMonitorModelOverlay, MarketMonitorSnapshotRequest
from tradingagents.web.market_monitor.service import MarketMonitorService
from tradingagents.web.market_monitor.universe import get_market_monitor_universe


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
            "tradingagents.web.market_monitor.service.build_market_dataset",
            return_value=dataset,
        ), patch.object(
            service._overlay_service,
            "create_overlay",
            return_value=MarketMonitorModelOverlay(status="skipped", notes=["test"]),
        ), patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            return_value=None,
        ), patch(
            "tradingagents.web.market_monitor.service.save_snapshot_cache",
        ) as mocked_save_cache:
            response = service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertFalse(response.rule_snapshot.ready)
        self.assertIn("SPY", response.rule_snapshot.missing_inputs)
        self.assertIsNone(response.rule_snapshot.long_term_score)
        self.assertEqual(response.rule_snapshot.source_coverage.data_freshness, "live_request_yfinance_daily")
        self.assertNotIn("fallback_placeholder", response.rule_snapshot.source_coverage.data_freshness)
        mocked_save_cache.assert_not_called()

    def test_failed_snapshot_persists_trace_snapshot(self) -> None:
        dataset = _dataset_missing_spy()
        with TemporaryDirectory() as temp_dir:
            service = MarketMonitorService(trace_root=Path(temp_dir))

            with patch(
                "tradingagents.web.market_monitor.service.build_market_dataset",
                return_value=dataset,
            ), patch.object(
                service._overlay_service,
                "create_overlay",
                side_effect=RuntimeError("overlay boom"),
            ), patch(
                "tradingagents.web.market_monitor.service.load_snapshot_cache",
                return_value=None,
            ):
                with self.assertRaisesRegex(RuntimeError, "overlay boom"):
                    service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

            traces = service.list_traces()
            self.assertEqual(len(traces), 1)
            self.assertEqual(traces[0].status, "failed")
            detail = service.get_trace_detail(traces[0].trace_id)
            self.assertEqual(detail.error["stage"], "snapshot")
            self.assertIn("overlay boom", detail.error["message"])
            logs = service.list_trace_logs(traces[0].trace_id)
            self.assertTrue(any(item.level == "Error" for item in logs))


if __name__ == "__main__":
    unittest.main()
