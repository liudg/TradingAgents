import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor import cache


class MarketMonitorCacheTests(unittest.TestCase):
    def test_load_symbol_daily_cache_ignores_unrelated_files(self) -> None:
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

    def test_load_snapshot_cache_returns_raw_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            market_monitor_dir = temp_path / "market_monitor"
            market_monitor_dir.mkdir()
            snapshot_path = market_monitor_dir / "snapshot_2026-04-10.json"
            snapshot_path.write_text(
                json.dumps({"as_of_date": "2026-04-10", "overall_confidence": 0.81}),
                encoding="utf-8",
            )

            with patch.object(cache, "MARKET_MONITOR_CACHE_DIR", market_monitor_dir):
                payload = cache.load_snapshot_cache(date(2026, 4, 10))

            self.assertEqual(payload, {"as_of_date": "2026-04-10", "overall_confidence": 0.81})

    def test_save_snapshot_cache_persists_raw_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            market_monitor_dir = temp_path / "market_monitor"
            market_monitor_dir.mkdir()

            with patch.object(cache, "MARKET_MONITOR_CACHE_DIR", market_monitor_dir):
                cache.save_snapshot_cache(date(2026, 4, 10), {"status": "ok"})
                saved = json.loads((market_monitor_dir / "snapshot_2026-04-10.json").read_text(encoding="utf-8"))

            self.assertEqual(saved, {"status": "ok"})

    def test_save_symbol_daily_cache_retries_replace_after_permission_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            market_monitor_dir = temp_path / "market_monitor"
            market_monitor_dir.mkdir()
            frame = pd.DataFrame(
                {
                    "Open": [1.0],
                    "High": [2.0],
                    "Low": [0.5],
                    "Close": [1.5],
                    "Volume": [100],
                },
                index=pd.to_datetime(["2026-04-10"]),
            )
            call_count = {"replace": 0}
            original_replace = Path.replace

            def flaky_replace(src: Path, target: Path) -> Path:
                if src.suffix == ".tmp" and target.name == "XLE_daily.csv":
                    call_count["replace"] += 1
                    if call_count["replace"] == 1:
                        raise PermissionError(5, "拒绝访问。")
                return original_replace(src, target)

            with patch.object(cache, "MARKET_MONITOR_CACHE_DIR", market_monitor_dir), patch.object(
                cache.Path,
                "replace",
                new=flaky_replace,
            ):
                cache.save_symbol_daily_cache("XLE", frame)

            self.assertEqual(call_count["replace"], 2)
            saved = pd.read_csv(market_monitor_dir / "XLE_daily.csv")
            self.assertEqual(saved.loc[0, "Close"], 1.5)


if __name__ == "__main__":
    unittest.main()
