import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from tradingagents.web.app import app, market_monitor_service
from tradingagents.web.market_monitor_schemas import MarketMonitorModelOverlay
from tradingagents.web.market_monitor_universe import get_market_monitor_universe


def _make_frame(base: float, days: int = 320) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp("2026-04-10"), periods=days, freq="B")
    close = pd.Series([base + i * 0.3 for i in range(days)], index=index)
    return pd.DataFrame(
        {
            "Open": close - 0.3,
            "High": close + 0.8,
            "Low": close - 0.8,
            "Close": close,
            "Volume": pd.Series([750_000 + i * 50 for i in range(days)], index=index),
        }
    )


def _complete_dataset() -> dict[str, dict[str, pd.DataFrame]]:
    universe = get_market_monitor_universe()
    core = {symbol: _make_frame(100 + idx * 2) for idx, symbol in enumerate(universe["core_index_etfs"])}
    core.update({symbol: _make_frame(80 + idx * 2) for idx, symbol in enumerate(universe["sector_etfs"])})
    core["^VIX"] = _make_frame(20)
    return {"core": core}


class MarketMonitorApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_snapshot_api_returns_rule_and_overlay_structure(self) -> None:
        dataset = _complete_dataset()
        skipped_overlay = MarketMonitorModelOverlay(status="skipped", notes=["test"])
        with patch(
            "tradingagents.web.market_monitor_service.build_market_dataset",
            return_value=dataset,
        ), patch.object(
            market_monitor_service._overlay_service,
            "create_overlay",
            return_value=skipped_overlay,
        ):
            response = self.client.get(
                "/api/market-monitor/snapshot",
                params={"as_of_date": date(2026, 4, 10).isoformat()},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("rule_snapshot", payload)
        self.assertIn("model_overlay", payload)
        self.assertIn("final_execution_card", payload)
        self.assertNotIn("fallback_placeholder", str(payload))
        self.assertTrue(payload["rule_snapshot"]["ready"])


if __name__ == "__main__":
    unittest.main()
