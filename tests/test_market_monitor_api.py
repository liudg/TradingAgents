import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from tradingagents.web.api.app import app, market_monitor_service
from tradingagents.web.market_monitor.schemas import MarketMonitorModelOverlay
from tradingagents.web.market_monitor.universe import get_market_monitor_universe


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
        self.temp_dir = TemporaryDirectory()
        market_monitor_service._dataset_cache.clear()
        market_monitor_service._trace_store = market_monitor_service._trace_store.__class__(
            Path(self.temp_dir.name)
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_snapshot_api_returns_rule_and_overlay_structure(self) -> None:
        dataset = _complete_dataset()
        skipped_overlay = MarketMonitorModelOverlay(status="skipped", notes=["test"])
        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            return_value=dataset,
        ), patch.object(
            market_monitor_service._overlay_service,
            "create_overlay",
            return_value=skipped_overlay,
        ), patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            return_value=None,
        ), patch(
            "tradingagents.web.market_monitor.service.save_snapshot_cache",
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
        self.assertIn("trace_id", payload)
        self.assertNotIn("fallback_placeholder", str(payload))
        self.assertTrue(payload["rule_snapshot"]["ready"])

        trace_id = payload["trace_id"]
        detail_response = self.client.get(f"/api/market-monitor/traces/{trace_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        self.assertEqual(detail_payload["trace_id"], trace_id)
        self.assertEqual(detail_payload["status"], "completed")
        self.assertEqual(detail_payload["overlay_status"], "skipped")
        self.assertTrue(detail_payload["dataset_summary"]["available_symbol_count"] > 0)
        self.assertEqual(detail_payload["response_summary"]["trace_id"], trace_id)
        self.assertNotIn("log_path", detail_payload)
        self.assertNotIn("snapshot_path", detail_payload)
        self.assertNotIn("queries", detail_payload["overlay_summary"])

        logs_response = self.client.get(f"/api/market-monitor/traces/{trace_id}/logs")
        self.assertEqual(logs_response.status_code, 200)
        logs_payload = logs_response.json()
        self.assertTrue(any(item["level"] == "Request" for item in logs_payload))
        self.assertTrue(any(item["level"] == "Rule" for item in logs_payload))
        self.assertTrue(any(item["level"] == "Response" for item in logs_payload))

        list_response = self.client.get("/api/market-monitor/traces", params={"limit": 5})
        self.assertEqual(list_response.status_code, 200)
        list_payload = list_response.json()
        self.assertEqual(len(list_payload), 1)
        self.assertEqual(list_payload[0]["trace_id"], trace_id)

    def test_snapshot_cache_hit_produces_trace_record(self) -> None:
        dataset = _complete_dataset()
        skipped_overlay = MarketMonitorModelOverlay(status="skipped", notes=["test"])
        cached_payload: dict[str, object] = {}

        def fake_load_snapshot_cache(_as_of_date: date) -> dict[str, object] | None:
            return cached_payload or None

        def fake_save_snapshot_cache(_as_of_date: date, payload: dict[str, object]) -> None:
            cached_payload.clear()
            cached_payload.update(payload)

        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            return_value=dataset,
        ), patch.object(
            market_monitor_service._overlay_service,
            "create_overlay",
            return_value=skipped_overlay,
        ), patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            side_effect=fake_load_snapshot_cache,
        ), patch(
            "tradingagents.web.market_monitor.service.save_snapshot_cache",
            side_effect=fake_save_snapshot_cache,
        ):
            first = self.client.get(
                "/api/market-monitor/snapshot",
                params={"as_of_date": date(2026, 4, 10).isoformat()},
            )
            second = self.client.get(
                "/api/market-monitor/snapshot",
                params={"as_of_date": date(2026, 4, 10).isoformat()},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        trace_id = second.json()["trace_id"]
        detail = self.client.get(f"/api/market-monitor/traces/{trace_id}").json()
        self.assertTrue(detail["cache_decision"]["snapshot_cache_hit"])
        self.assertTrue(detail["response_summary"]["served_from_snapshot_cache"])
        self.assertEqual(detail["dataset_summary"]["source"], "snapshot_cache")
        self.assertIn("ready", detail["rule_snapshot_summary"])
        self.assertIn("status", detail["overlay_summary"])
        self.assertIn("final_regime_label", detail["final_execution_summary"])
        logs_payload = self.client.get(f"/api/market-monitor/traces/{trace_id}/logs").json()
        self.assertTrue(any("Returning cached snapshot" in item["content"] for item in logs_payload))


if __name__ == "__main__":
    unittest.main()
