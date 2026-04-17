import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.data import (
    _download_single_symbol,
    _get_symbol_history,
    _is_cache_usable,
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

    def test_cache_is_usable_when_expected_close_is_present_and_rows_are_sufficient(self) -> None:
        frame = _make_frame(_required_trading_days(420), end="2026-04-10")

        self.assertTrue(_is_cache_usable(frame, date(2026, 4, 12), 420))

    def test_cache_is_not_usable_when_expected_close_is_missing(self) -> None:
        frame = _make_frame(_required_trading_days(420), end="2026-04-09")

        self.assertFalse(_is_cache_usable(frame, date(2026, 4, 12), 420))

    def test_cache_is_not_usable_when_rows_are_insufficient(self) -> None:
        frame = _make_frame(_required_trading_days(420) - 1, end="2026-04-10")

        self.assertFalse(_is_cache_usable(frame, date(2026, 4, 12), 420))

    def test_get_symbol_history_returns_stale_fallback_when_refresh_fails(self) -> None:
        cached = _make_frame(_required_trading_days(420), end="2026-04-09")

        with patch(
            "tradingagents.web.market_monitor.data.load_symbol_daily_cache",
            return_value=cached,
        ), patch(
            "tradingagents.web.market_monitor.data._download_single_symbol",
            return_value=pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]),
        ):
            result = _get_symbol_history("SPY", date(2026, 4, 12), 420)

        self.assertEqual(result.cache_state, "stale_fallback")
        self.assertFalse(result.fetched_live)
        self.assertEqual(len(result.frame), len(cached))

    def test_fetch_daily_history_returns_cache_summary_counts(self) -> None:
        hit = _make_frame(_required_trading_days(420), end="2026-04-10")
        stale = _make_frame(_required_trading_days(420), end="2026-04-09")

        with patch(
            "tradingagents.web.market_monitor.data._get_symbol_history",
            side_effect=[
                type("History", (), {"frame": hit, "cache_state": "cache_hit", "fetched_live": False, "expected_close_date": pd.Timestamp("2026-04-10")})(),
                type("History", (), {"frame": stale, "cache_state": "stale_fallback", "fetched_live": False, "expected_close_date": pd.Timestamp("2026-04-10")})(),
            ],
        ):
            frames, summary = fetch_daily_history(["SPY", "QQQ"], date(2026, 4, 12), 420)

        self.assertEqual(set(frames.keys()), {"SPY", "QQQ"})
        self.assertEqual(summary["counts"]["cache_hit"], 1)
        self.assertEqual(summary["counts"]["stale_fallback"], 1)


if __name__ == "__main__":
    unittest.main()
