import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor import cache, io_utils


class MarketMonitorCacheTests(unittest.TestCase):
    def _frame(self, days: int = 260, end: str = "2026-04-10") -> pd.DataFrame:
        index = pd.date_range(end=pd.Timestamp(end), periods=days, freq="B")
        close = pd.Series(range(days), index=index, dtype=float)
        return pd.DataFrame(
            {
                "Open": close + 1,
                "High": close + 2,
                "Low": close,
                "Close": close + 1.5,
                "Volume": pd.Series([1000] * days, index=index),
            }
        )

    def test_load_symbol_daily_cache_returns_missing_when_symbol_dir_absent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            symbols_dir = Path(temp_dir) / "market_monitor" / "symbols"
            symbols_dir.mkdir(parents=True)

            with patch.object(cache, "MARKET_MONITOR_SYMBOLS_DIR", symbols_dir):
                result = cache.load_symbol_daily_cache_record("SPY", date(2026, 4, 10))

            self.assertEqual(result.state, "cache_missing")
            self.assertTrue(result.frame.empty)

    def test_save_symbol_daily_cache_writes_meta_and_csv(self) -> None:
        with TemporaryDirectory() as temp_dir:
            symbols_dir = Path(temp_dir) / "market_monitor" / "symbols"
            symbols_dir.mkdir(parents=True)
            frame = self._frame()

            with patch.object(cache, "MARKET_MONITOR_SYMBOLS_DIR", symbols_dir):
                cache.save_symbol_daily_cache(
                    "XLE",
                    frame,
                    as_of_date=date(2026, 4, 10),
                    expected_close_date=date(2026, 4, 10),
                    required_rows=252,
                    now=datetime(2026, 4, 10, tzinfo=timezone.utc),
                )

            symbol_dir = symbols_dir / "XLE"
            self.assertTrue((symbol_dir / "meta.json").exists())
            self.assertTrue((symbol_dir / "daily.csv").exists())
            saved = pd.read_csv(symbol_dir / "daily.csv")
            self.assertEqual(saved.loc[0, "Close"], frame.reset_index().loc[0, "Close"])

    def test_load_symbol_daily_cache_returns_corrupted_for_invalid_meta_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            symbol_dir = Path(temp_dir) / "market_monitor" / "symbols" / "SPY"
            symbol_dir.mkdir(parents=True)
            (symbol_dir / "meta.json").write_text('{"broken":', encoding="utf-8")
            self._frame().reset_index(names="Date").to_csv(symbol_dir / "daily.csv", index=False)

            with patch.object(cache, "MARKET_MONITOR_SYMBOLS_DIR", symbol_dir.parent):
                result = cache.load_symbol_daily_cache_record("SPY", date(2026, 4, 10))

            self.assertEqual(result.state, "cache_corrupted")
            self.assertIn("元数据", result.reason or "")

    def test_load_symbol_daily_cache_returns_invalid_structure_for_duplicate_index(self) -> None:
        with TemporaryDirectory() as temp_dir:
            symbols_dir = Path(temp_dir) / "market_monitor" / "symbols"
            symbols_dir.mkdir(parents=True)
            frame = self._frame()
            duplicate = frame.iloc[[-1]].copy()
            duplicate.index = pd.DatetimeIndex([frame.index[-2]])
            with_duplicates = pd.concat([frame.iloc[:-1], duplicate]).sort_index()

            with patch.object(cache, "MARKET_MONITOR_SYMBOLS_DIR", symbols_dir):
                cache.save_symbol_daily_cache(
                    "SPY",
                    frame,
                    as_of_date=date(2026, 4, 10),
                    expected_close_date=date(2026, 4, 10),
                    required_rows=252,
                    now=datetime(2026, 4, 10, tzinfo=timezone.utc),
                )
                with_duplicates.reset_index(names="Date").to_csv(symbols_dir / "SPY" / "daily.csv", index=False)
                result = cache.load_symbol_daily_cache_record("SPY", date(2026, 4, 10))

            self.assertEqual(result.state, "cache_invalid_structure")
            self.assertIn("重复日期", result.reason or "")

    def test_evaluate_symbol_daily_cache_returns_hit_when_metadata_is_fresh(self) -> None:
        with TemporaryDirectory() as temp_dir:
            symbols_dir = Path(temp_dir) / "market_monitor" / "symbols"
            symbols_dir.mkdir(parents=True)
            frame = self._frame(days=320)

            with patch.object(cache, "MARKET_MONITOR_SYMBOLS_DIR", symbols_dir):
                cache.save_symbol_daily_cache(
                    "SPY",
                    frame,
                    as_of_date=date(2026, 4, 10),
                    expected_close_date=date(2026, 4, 10),
                    required_rows=252,
                    now=datetime(2026, 4, 10, tzinfo=timezone.utc),
                )
                result = cache.evaluate_symbol_daily_cache(
                    "SPY",
                    date(2026, 4, 12),
                    252,
                    date(2026, 4, 10),
                    now=datetime(2026, 4, 12, tzinfo=timezone.utc),
                )

            self.assertEqual(result.state, "cache_hit")

    def test_load_symbol_daily_cache_record_allows_requesting_earlier_as_of_date(self) -> None:
        with TemporaryDirectory() as temp_dir:
            symbols_dir = Path(temp_dir) / "market_monitor" / "symbols"
            symbols_dir.mkdir(parents=True)
            frame = self._frame(days=320)

            with patch.object(cache, "MARKET_MONITOR_SYMBOLS_DIR", symbols_dir):
                cache.save_symbol_daily_cache(
                    "SPY",
                    frame,
                    as_of_date=date(2026, 4, 10),
                    expected_close_date=date(2026, 4, 10),
                    required_rows=252,
                    now=datetime(2026, 4, 10, tzinfo=timezone.utc),
                )
                result = cache.load_symbol_daily_cache_record("SPY", date(2026, 4, 8))

            self.assertEqual(result.state, "cache_hit")
            self.assertEqual(result.cache_end_date, date(2026, 4, 10))
            self.assertEqual(result.frame.index.max().date(), date(2026, 4, 8))

    def test_evaluate_symbol_daily_cache_returns_stale_from_metadata_not_mtime(self) -> None:
        with TemporaryDirectory() as temp_dir:
            symbols_dir = Path(temp_dir) / "market_monitor" / "symbols"
            symbols_dir.mkdir(parents=True)
            frame = self._frame(days=320)

            with patch.object(cache, "MARKET_MONITOR_SYMBOLS_DIR", symbols_dir):
                cache.save_symbol_daily_cache(
                    "SPY",
                    frame,
                    as_of_date=date(2026, 4, 10),
                    expected_close_date=date(2026, 4, 10),
                    required_rows=252,
                    now=datetime(2026, 4, 10, tzinfo=timezone.utc),
                )
                data_path = symbols_dir / "SPY" / "daily.csv"
                recent_ts = datetime(2026, 4, 20, tzinfo=timezone.utc).timestamp()
                import os
                os.utime(data_path, (recent_ts, recent_ts))
                result = cache.evaluate_symbol_daily_cache(
                    "SPY",
                    date(2026, 4, 20),
                    252,
                    date(2026, 4, 10),
                    now=datetime(2026, 4, 20, tzinfo=timezone.utc),
                )

            self.assertEqual(result.state, "cache_stale")
            self.assertIn("刷新时间", result.reason or "")

    def test_cleanup_symbol_daily_cache_removes_expired_symbol_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            symbols_dir = Path(temp_dir) / "market_monitor" / "symbols"
            symbols_dir.mkdir(parents=True)
            frame = self._frame()

            with patch.object(cache, "MARKET_MONITOR_SYMBOLS_DIR", symbols_dir):
                cache.save_symbol_daily_cache(
                    "SPY",
                    frame,
                    as_of_date=date(2026, 3, 1),
                    expected_close_date=date(2026, 3, 1),
                    required_rows=252,
                    now=datetime(2026, 3, 1, tzinfo=timezone.utc),
                )
                meta_path = symbols_dir / "SPY" / "meta.json"
                payload = __import__("json").loads(meta_path.read_text(encoding="utf-8"))
                payload["retention_expires_on"] = "2026-03-15"
                meta_path.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                removed = cache.cleanup_symbol_daily_cache(30, now=datetime(2026, 4, 17, tzinfo=timezone.utc))

            self.assertEqual(removed, 1)
            self.assertFalse((symbols_dir / "SPY").exists())

    def test_cleanup_symbol_daily_cache_removes_corrupt_symbol_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            symbols_dir = Path(temp_dir) / "market_monitor" / "symbols"
            symbol_dir = symbols_dir / "SPY"
            symbol_dir.mkdir(parents=True)
            (symbol_dir / "unexpected.txt").write_text("broken", encoding="utf-8")

            with patch.object(cache, "MARKET_MONITOR_SYMBOLS_DIR", symbols_dir):
                removed = cache.cleanup_symbol_daily_cache(30, now=datetime(2026, 4, 17, tzinfo=timezone.utc))

            self.assertEqual(removed, 1)
            self.assertFalse(symbol_dir.exists())

    def test_cleanup_symbol_daily_cache_keeps_inflight_directory_without_meta(self) -> None:
        with TemporaryDirectory() as temp_dir:
            symbols_dir = Path(temp_dir) / "market_monitor" / "symbols"
            symbol_dir = symbols_dir / "SPY"
            symbol_dir.mkdir(parents=True)
            (symbol_dir / "daily.csv").write_text("Date,Open,High,Low,Close,Volume\n2026-04-10,1,2,0,1.5,100\n", encoding="utf-8")

            with patch.object(cache, "MARKET_MONITOR_SYMBOLS_DIR", symbols_dir):
                removed = cache.cleanup_symbol_daily_cache(30, now=datetime(2026, 4, 17, tzinfo=timezone.utc))

            self.assertEqual(removed, 0)
            self.assertTrue(symbol_dir.exists())

    def test_json_atomic_write_retries_replace_after_permission_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "payload.json"
            call_count = {"replace": 0}
            original_replace = Path.replace

            def flaky_replace(src: Path, dest: Path) -> Path:
                if src.suffix == ".tmp" and dest.name == "payload.json":
                    call_count["replace"] += 1
                    if call_count["replace"] == 1:
                        raise PermissionError(5, "拒绝访问。")
                return original_replace(src, dest)

            with patch.object(io_utils.Path, "replace", new=flaky_replace):
                io_utils.write_json_atomic(target, {"status": "ok"})

            self.assertEqual(call_count["replace"], 2)
            self.assertIn('"status": "ok"', target.read_text(encoding="utf-8"))

    def test_csv_atomic_write_retries_replace_after_permission_error(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            target = temp_path / "payload.csv"
            frame = self._frame(days=1).reset_index(names="Date")
            call_count = {"replace": 0}
            original_replace = Path.replace

            def flaky_replace(src: Path, dest: Path) -> Path:
                if src.suffix == ".tmp" and dest.name == "payload.csv":
                    call_count["replace"] += 1
                    if call_count["replace"] == 1:
                        raise PermissionError(5, "拒绝访问。")
                return original_replace(src, dest)

            with patch.object(io_utils.Path, "replace", new=flaky_replace):
                io_utils.write_dataframe_csv_atomic(target, frame)

            self.assertEqual(call_count["replace"], 2)
            saved = pd.read_csv(target)
            self.assertEqual(saved.loc[0, "Close"], frame.loc[0, "Close"])


if __name__ == "__main__":
    unittest.main()
