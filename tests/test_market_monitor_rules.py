import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.data import _expected_market_close_date, _is_cache_usable
from tradingagents.web.market_monitor.metrics import build_market_snapshot
from tradingagents.web.market_monitor.schemas import MarketMonitorSnapshotRequest
from tradingagents.web.market_monitor.service import MarketMonitorService
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


def _complete_dataset() -> dict[str, dict[str, pd.DataFrame]]:
    universe = get_market_monitor_universe()
    core = {symbol: _make_frame(100 + idx * 3) for idx, symbol in enumerate(universe["core_index_etfs"])}
    core.update({symbol: _make_frame(80 + idx * 2) for idx, symbol in enumerate(universe["sector_etfs"])})
    core["^VIX"] = _make_frame(18, days=320)
    return {"core": core}


class MarketMonitorRulesTests(unittest.TestCase):
    def test_symbol_cache_requires_requested_trading_day(self) -> None:
        friday_frame = _make_frame(100, days=120)

        self.assertFalse(_is_cache_usable(friday_frame, date(2026, 4, 13), 60))
        self.assertTrue(_is_cache_usable(friday_frame, date(2026, 4, 12), 60))
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

    def test_snapshot_uses_cache_between_requests(self) -> None:
        service = MarketMonitorService()
        dataset = _complete_dataset()
        cached_payload: dict[str, object] = {}

        def fake_load_snapshot_cache(_as_of_date: date) -> dict[str, object] | None:
            return cached_payload or None

        def fake_save_snapshot_cache(_as_of_date: date, payload: dict[str, object]) -> None:
            cached_payload.clear()
            cached_payload.update(payload)

        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            return_value=dataset,
        ) as mocked_dataset, patch.object(
            service._assessment_service,
            "create_assessment",
            return_value=(service._assessment_service._build_error_assessment("test"), [], [], 0.1),
        ), patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            side_effect=fake_load_snapshot_cache,
        ) as mocked_load_cache, patch(
            "tradingagents.web.market_monitor.service.save_snapshot_cache",
            side_effect=fake_save_snapshot_cache,
        ):
            service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))
            service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertEqual(mocked_dataset.call_count, 1)
        self.assertEqual(mocked_load_cache.call_count, 2)


if __name__ == "__main__":
    unittest.main()
