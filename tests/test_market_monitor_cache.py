import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor import cache


class MarketMonitorCacheTests(unittest.TestCase):
    def test_load_symbol_daily_cache_does_not_fallback_to_legacy_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            market_monitor_dir = temp_path / "market_monitor"
            market_monitor_dir.mkdir()

            legacy_file = temp_path / "SPY-YFin-data-2026-04-10.csv"
            pd.DataFrame(
                {
                    "Date": ["2026-04-09", "2026-04-10"],
                    "Close": [100.0, 101.0],
                }
            ).to_csv(legacy_file, index=False)

            with patch.object(cache, "MARKET_MONITOR_CACHE_DIR", market_monitor_dir):
                frame = cache.load_symbol_daily_cache("SPY", date(2026, 4, 10))

            self.assertTrue(frame.empty)

    def test_load_snapshot_cache_rejects_legacy_raw_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            market_monitor_dir = temp_path / "market_monitor"
            market_monitor_dir.mkdir()
            snapshot_path = market_monitor_dir / "snapshot_2026-04-10.json"
            snapshot_path.write_text(
                json.dumps({"as_of_date": "2026-04-10", "rule_snapshot": {"ready": True}}),
                encoding="utf-8",
            )

            with patch.object(cache, "MARKET_MONITOR_CACHE_DIR", market_monitor_dir):
                payload = cache.load_snapshot_cache(date(2026, 4, 10))

            self.assertIsNone(payload)

    def test_save_snapshot_cache_wraps_payload_with_current_version(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            market_monitor_dir = temp_path / "market_monitor"
            market_monitor_dir.mkdir()

            with patch.object(cache, "MARKET_MONITOR_CACHE_DIR", market_monitor_dir):
                cache.save_snapshot_cache(date(2026, 4, 10), {"status": "ok"})
                saved = json.loads((market_monitor_dir / "snapshot_2026-04-10.json").read_text(encoding="utf-8"))

            self.assertEqual(saved["cache_version"], 1)
            self.assertEqual(saved["snapshot"], {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
