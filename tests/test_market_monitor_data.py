import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.data import (
    _download_single_symbol,
    _get_symbol_history,
    _required_trading_days,
    fetch_daily_history,
)


class _FakeYFinance:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def download(self, **kwargs):
        self.calls.append(kwargs)
        return pd.DataFrame()


def _make_frame(days: int, end: str = "2026-04-10") -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp(end), periods=days, freq="B")
    close = pd.Series(range(days), index=index, dtype=float)
    return pd.DataFrame(
        {
            "Open": close + 1,
            "High": close + 2,
            "Low": close,
            "Close": close + 1.5,
            "Volume": pd.Series([1_000] * days, index=index),
        }
    )


def _cache_result(state: str, frame: pd.DataFrame | None = None, reason: str | None = None):
    return type(
        "CacheResult",
        (),
        {
            "state": state,
            "frame": frame if frame is not None else pd.DataFrame(),
            "reason": reason,
            "cache_end_date": frame.index.max().date() if frame is not None and not frame.empty else None,
            "last_successful_refresh_at": datetime(2026, 4, 10, tzinfo=timezone.utc),
            "metadata": None,
        },
    )()


class MarketMonitorDataTests(unittest.TestCase):
    def test_download_single_symbol_sets_network_timeout(self) -> None:
        fake_yf = _FakeYFinance()

        with patch("tradingagents.web.market_monitor.data.get_yf", return_value=fake_yf):
            frame = _download_single_symbol("XLC", date(2026, 4, 12), 30)

        self.assertTrue(frame.empty)
        self.assertEqual(fake_yf.calls[0]["timeout"], 10)

    def test_download_single_symbol_does_not_retry_empty_failed_downloads(self) -> None:
        fake_yf = _FakeYFinance()

        with patch("tradingagents.web.market_monitor.data.get_yf", return_value=fake_yf):
            frame = _download_single_symbol("XLC", date(2026, 4, 12), 30)

        self.assertTrue(frame.empty)
        self.assertEqual(len(fake_yf.calls), 1)

    def test_get_symbol_history_returns_cache_hit_for_fresh_valid_cache(self) -> None:
        cached = _make_frame(_required_trading_days(420), end="2026-04-10")

        with patch(
            "tradingagents.web.market_monitor.data.evaluate_symbol_daily_cache",
            return_value=_cache_result("cache_hit", cached),
        ):
            result = _get_symbol_history("SPY", date(2026, 4, 12), 420)

        self.assertEqual(result.cache_state, "cache_hit")
        self.assertEqual(result.result_state, "cache_hit")
        self.assertFalse(result.fetched_live)

    def test_get_symbol_history_returns_stale_fallback_only_for_cache_stale(self) -> None:
        cached = _make_frame(_required_trading_days(420), end="2026-04-09")

        with patch(
            "tradingagents.web.market_monitor.data.evaluate_symbol_daily_cache",
            return_value=_cache_result("cache_stale", cached, "缓存刷新时间超出允许范围"),
        ), patch(
            "tradingagents.web.market_monitor.data._download_single_symbol",
            return_value=pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]),
        ):
            result = _get_symbol_history("SPY", date(2026, 4, 12), 420)

        self.assertEqual(result.cache_state, "cache_stale")
        self.assertEqual(result.result_state, "stale_fallback")
        self.assertFalse(result.fetched_live)

    def test_get_symbol_history_does_not_fallback_for_invalid_structure(self) -> None:
        cached = _make_frame(_required_trading_days(420), end="2026-04-09")

        with patch(
            "tradingagents.web.market_monitor.data.evaluate_symbol_daily_cache",
            return_value=_cache_result("cache_invalid_structure", cached, "缓存索引存在重复日期"),
        ), patch(
            "tradingagents.web.market_monitor.data._download_single_symbol",
            return_value=pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]),
        ):
            result = _get_symbol_history("SPY", date(2026, 4, 12), 420)

        self.assertEqual(result.cache_state, "cache_invalid_structure")
        self.assertEqual(result.result_state, "empty")
        self.assertTrue(result.frame.empty)

    def test_get_symbol_history_force_refresh_bypasses_cache_hit(self) -> None:
        cached = _make_frame(_required_trading_days(420), end="2026-04-10")
        fresh = _make_frame(_required_trading_days(420), end="2026-04-10")

        with patch(
            "tradingagents.web.market_monitor.data.evaluate_symbol_daily_cache",
            return_value=_cache_result("cache_hit", cached),
        ), patch(
            "tradingagents.web.market_monitor.data._download_single_symbol",
            return_value=fresh,
        ) as download_mock, patch(
            "tradingagents.web.market_monitor.data.save_symbol_daily_cache"
        ) as save_mock:
            result = _get_symbol_history("SPY", date(2026, 4, 12), 420, force_refresh=True)

        self.assertEqual(result.cache_state, "cache_hit")
        self.assertEqual(result.result_state, "refreshed")
        self.assertTrue(result.fetched_live)
        download_mock.assert_called_once()
        save_mock.assert_called_once()

    def test_get_symbol_history_returns_empty_without_cache_when_refresh_fails(self) -> None:
        with patch(
            "tradingagents.web.market_monitor.data.evaluate_symbol_daily_cache",
            return_value=_cache_result("cache_missing"),
        ), patch(
            "tradingagents.web.market_monitor.data._download_single_symbol",
            return_value=pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]),
        ):
            result = _get_symbol_history("SPY", date(2026, 4, 12), 420)

        self.assertEqual(result.cache_state, "cache_missing")
        self.assertEqual(result.result_state, "empty")
        self.assertTrue(result.frame.empty)

    def test_fetch_daily_history_returns_cache_summary_counts(self) -> None:
        hit = _make_frame(_required_trading_days(420), end="2026-04-10")
        stale = _make_frame(_required_trading_days(420), end="2026-04-09")

        with patch(
            "tradingagents.web.market_monitor.data._get_symbol_history",
            side_effect=[
                type("History", (), {
                    "frame": hit,
                    "cache_state": "cache_hit",
                    "result_state": "cache_hit",
                    "fetched_live": False,
                    "expected_close_date": pd.Timestamp("2026-04-10"),
                    "reason": None,
                    "cache_end_date": "2026-04-10",
                    "last_successful_refresh_at": "2026-04-10T00:00:00+00:00",
                })(),
                type("History", (), {
                    "frame": stale,
                    "cache_state": "cache_stale",
                    "result_state": "stale_fallback",
                    "fetched_live": False,
                    "expected_close_date": pd.Timestamp("2026-04-10"),
                    "reason": "缓存刷新时间超出允许范围",
                    "cache_end_date": "2026-04-09",
                    "last_successful_refresh_at": "2026-04-10T00:00:00+00:00",
                })(),
            ],
        ):
            frames, summary = fetch_daily_history(["SPY", "QQQ"], date(2026, 4, 12), 420)

        self.assertEqual(set(frames.keys()), {"SPY", "QQQ"})
        self.assertEqual(summary["counts"]["cache_hit"], 1)
        self.assertEqual(summary["counts"]["cache_stale"], 1)
        self.assertEqual(summary["result_counts"]["stale_fallback"], 1)
        self.assertIn("reason", summary["symbols"][0])
        self.assertIn("result_state", summary["symbols"][0])


if __name__ == "__main__":
    unittest.main()
