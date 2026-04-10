import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor_schemas import MarketMonitorModelOverlay, MarketMonitorSnapshotRequest
from tradingagents.web.market_monitor_service import MarketMonitorService
from tradingagents.web.market_monitor_universe import get_market_monitor_universe


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
    nasdaq = {symbol: _make_frame(50 + idx) for idx, symbol in enumerate(universe["nasdaq_100"][:25])}
    return {"core": core, "nasdaq_100": nasdaq}


class MarketMonitorRulesTests(unittest.TestCase):
    def test_snapshot_does_not_cache_between_requests(self) -> None:
        service = MarketMonitorService()
        dataset = _complete_dataset()

        with patch(
            "tradingagents.web.market_monitor_service.build_market_dataset",
            side_effect=[dataset, dataset],
        ) as mocked_dataset, patch.object(
            service._overlay_service,
            "create_overlay",
            return_value=MarketMonitorModelOverlay(status="skipped", notes=["test"]),
        ):
            service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))
            service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertEqual(mocked_dataset.call_count, 2)


if __name__ == "__main__":
    unittest.main()
