import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

import pandas as pd

from tradingagents.dataflows.yfinance_news import fetch_global_news_articles_yfinance
from tradingagents.web.market_monitor.data import (
    _download_single_symbol,
    _evaluate_intraday_symbol_state,
    _get_symbol_history,
    _market_data_mode_policy,
    _required_trading_days,
    build_market_dataset,
    fetch_daily_history,
    fetch_intraday_history,
)
from tradingagents.web.market_monitor.universe import get_market_monitor_universe


class _FakeYFinance:
    def __init__(self, frame: pd.DataFrame | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.frame = frame

    def download(self, **kwargs):
        self.calls.append(kwargs)
        return self.frame if self.frame is not None else pd.DataFrame()


class _FakeSearchResult:
    news = [
        {
            "content": {
                "title": "Fed signals rates may stay higher",
                "summary": "Policy makers discussed inflation risk.",
                "provider": {"displayName": "Reuters"},
                "canonicalUrl": {"url": "https://example.com/fed-rates"},
                "pubDate": "2026-04-11T12:00:00Z",
            }
        }
    ]


class _FakeNewsYFinance:
    def Search(self, **kwargs):
        return _FakeSearchResult()


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


def _make_intraday_frame(end: str = "2026-04-10 15:55", periods: int = 6) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp(end), periods=periods, freq="5min")
    close = pd.Series(range(periods), index=index, dtype=float)
    return pd.DataFrame(
        {
            "Open": close + 1,
            "High": close + 2,
            "Low": close,
            "Close": close + 1.5,
            "Volume": pd.Series([1_000] * periods, index=index),
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
    def test_fetch_global_news_articles_returns_structured_nested_articles(self) -> None:
        with patch("tradingagents.dataflows.yfinance_news.get_yf", return_value=_FakeNewsYFinance()), patch(
            "tradingagents.dataflows.yfinance_news.yf_retry",
            side_effect=lambda func: func(),
        ):
            articles = fetch_global_news_articles_yfinance("2026-04-12", look_back_days=7, limit=1)

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Fed signals rates may stay higher")
        self.assertEqual(articles[0]["publisher"], "Reuters")
        self.assertEqual(articles[0]["link"], "https://example.com/fed-rates")
        self.assertEqual(articles[0]["pub_date"], datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc))

    def test_build_market_dataset_can_skip_event_news(self) -> None:
        universe = get_market_monitor_universe()
        with patch("tradingagents.web.market_monitor.data.fetch_daily_history", return_value=({}, {"symbols": []})), patch(
            "tradingagents.web.market_monitor.data.fetch_global_news_articles_yfinance",
            side_effect=AssertionError("global news should not be fetched"),
        ), patch(
            "tradingagents.web.market_monitor.data.fetch_ticker_news_articles_yfinance",
            side_effect=AssertionError("ticker news should not be fetched"),
        ):
            dataset = build_market_dataset(universe, date(2026, 4, 12), include_event_news=False)

        self.assertEqual(dataset["search"]["event_fact_candidates"], [])
        self.assertEqual(dataset["search"]["status"]["source"], "disabled_for_history")
        self.assertEqual(dataset["search"]["status"]["event_fact_candidate_count"], 0)

    def test_build_market_dataset_injects_news_event_candidates(self) -> None:
        universe = get_market_monitor_universe()
        article = {
            "title": "CPI data lifts inflation concerns",
            "summary": "Investors prepared for a hotter CPI print.",
            "publisher": "Reuters",
            "link": "https://example.com/cpi",
            "pub_date": datetime(2026, 4, 11, 13, 0, tzinfo=timezone.utc),
        }

        with patch("tradingagents.web.market_monitor.data.fetch_daily_history", return_value=({}, {"symbols": []})), patch(
            "tradingagents.web.market_monitor.data.fetch_global_news_articles_yfinance",
            return_value=[article],
        ), patch("tradingagents.web.market_monitor.data.fetch_ticker_news_articles_yfinance", return_value=[]):
            dataset = build_market_dataset(universe, date(2026, 4, 12))

        candidates = dataset["search"]["event_fact_candidates"]
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["event"], "CPI data lifts inflation concerns")
        self.assertEqual(candidates[0]["scope"], "index_level")
        self.assertEqual(candidates[0]["severity"], "high")
        self.assertEqual(candidates[0]["source_name"], "Reuters")
        self.assertEqual(candidates[0]["source_url"], "https://example.com/cpi")
        self.assertEqual(dataset["search"]["status"]["event_fact_candidate_count"], 1)

    def test_build_market_dataset_drops_news_with_unauditable_url(self) -> None:
        universe = get_market_monitor_universe()
        article = {
            "title": "Fed signals rates may stay higher",
            "summary": "Policy makers discussed inflation risk.",
            "publisher": "Reuters",
            "link": "javascript:alert(1)",
            "pub_date": datetime(2026, 4, 11, 13, 0, tzinfo=timezone.utc),
        }

        with patch("tradingagents.web.market_monitor.data.fetch_daily_history", return_value=({}, {"symbols": []})), patch(
            "tradingagents.web.market_monitor.data.fetch_global_news_articles_yfinance",
            return_value=[article],
        ), patch("tradingagents.web.market_monitor.data.fetch_ticker_news_articles_yfinance", return_value=[]):
            dataset = build_market_dataset(universe, date(2026, 4, 12))

        self.assertEqual(dataset["search"]["event_fact_candidates"], [])
        self.assertEqual(dataset["search"]["status"]["global_news_count"], 1)
        self.assertEqual(dataset["search"]["status"]["event_fact_candidate_count"], 0)

    def test_build_market_dataset_records_news_failure_without_fabricated_events(self) -> None:
        universe = get_market_monitor_universe()
        with patch("tradingagents.web.market_monitor.data.fetch_daily_history", return_value=({}, {"symbols": []})), patch(
            "tradingagents.web.market_monitor.data.fetch_global_news_articles_yfinance",
            side_effect=RuntimeError("network down"),
        ), patch("tradingagents.web.market_monitor.data.fetch_ticker_news_articles_yfinance", return_value=[]):
            dataset = build_market_dataset(universe, date(2026, 4, 12))

        self.assertEqual(dataset["search"]["event_fact_candidates"], [])
        self.assertEqual(dataset["search"]["status"]["event_fact_candidate_count"], 0)
        self.assertTrue(dataset["search"]["status"]["errors"])

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

    def test_fetch_intraday_delayed_uses_five_minute_no_prepost(self) -> None:
        fake_yf = _FakeYFinance(_make_intraday_frame())

        with patch("tradingagents.web.market_monitor.data.get_yf", return_value=fake_yf):
            frames, summary = fetch_intraday_history(["SPY"], date(2026, 4, 10), "intraday_delayed")

        self.assertFalse(frames["SPY"].empty)
        self.assertEqual(fake_yf.calls[0]["interval"], "5m")
        self.assertFalse(fake_yf.calls[0]["prepost"])
        self.assertEqual(summary["data_mode"], "intraday_delayed")
        self.assertEqual(summary["interval"], "5m")
        self.assertFalse(summary["includes_prepost"])
        self.assertEqual(summary["result_counts"]["refreshed"], 1)
        self.assertFalse(summary["symbols"][0]["partial"])

    def test_fetch_intraday_realtime_uses_one_minute_prepost(self) -> None:
        fake_yf = _FakeYFinance(_make_intraday_frame(end="2026-04-10 16:00", periods=3))

        with patch("tradingagents.web.market_monitor.data.get_yf", return_value=fake_yf):
            _, summary = fetch_intraday_history(["SPY"], date(2026, 4, 10), "intraday_realtime")

        self.assertEqual(fake_yf.calls[0]["interval"], "1m")
        self.assertTrue(fake_yf.calls[0]["prepost"])
        self.assertEqual(summary["interval"], "1m")
        self.assertTrue(summary["includes_prepost"])

    def test_intraday_current_day_after_close_complete_bar_is_fresh(self) -> None:
        policy = _market_data_mode_policy("intraday_delayed")
        frame = _make_intraday_frame(end="2026-04-10 15:55")

        result_state, partial, reason = _evaluate_intraday_symbol_state(
            frame,
            date(2026, 4, 10),
            policy,
            now=datetime(2026, 4, 10, 16, 30),
        )

        self.assertEqual(result_state, "refreshed")
        self.assertFalse(partial)
        self.assertIsNone(reason)

    def test_intraday_historical_incomplete_session_is_stale(self) -> None:
        policy = _market_data_mode_policy("intraday_delayed")
        frame = _make_intraday_frame(end="2026-04-10 10:00")

        result_state, partial, reason = _evaluate_intraday_symbol_state(
            frame,
            date(2026, 4, 10),
            policy,
            now=datetime(2026, 4, 11, 10, 30),
        )

        self.assertEqual(result_state, "stale_fallback")
        self.assertTrue(partial)
        self.assertIn("完整收盘时段", reason)

    def test_intraday_current_day_during_session_stale_uses_age_threshold(self) -> None:
        policy = _market_data_mode_policy("intraday_realtime")
        frame = _make_intraday_frame(end="2026-04-10 10:00", periods=3)

        result_state, partial, reason = _evaluate_intraday_symbol_state(
            frame,
            date(2026, 4, 10),
            policy,
            now=datetime(2026, 4, 10, 10, 30),
        )

        self.assertEqual(result_state, "stale_fallback")
        self.assertTrue(partial)
        self.assertIn("10 分钟", reason)

    def test_fetch_intraday_empty_result_is_deterministic(self) -> None:
        fake_yf = _FakeYFinance()

        with patch("tradingagents.web.market_monitor.data.get_yf", return_value=fake_yf):
            frames, summary = fetch_intraday_history(["SPY"], date(2026, 4, 10), "intraday_delayed")

        self.assertTrue(frames["SPY"].empty)
        self.assertEqual(summary["result_counts"]["empty"], 1)
        self.assertEqual(summary["symbols"][0]["result_state"], "empty")
        self.assertIn("5m", summary["symbols"][0]["reason"])

    def test_fetch_intraday_stale_result_keeps_non_empty_data(self) -> None:
        fake_yf = _FakeYFinance(_make_intraday_frame(end="2026-04-09 16:00"))

        with patch("tradingagents.web.market_monitor.data.get_yf", return_value=fake_yf):
            frames, summary = fetch_intraday_history(["SPY"], date(2026, 4, 10), "intraday_delayed")

        self.assertFalse(frames["SPY"].empty)
        self.assertEqual(summary["result_counts"]["stale_fallback"], 1)
        self.assertEqual(summary["symbols"][0]["result_state"], "stale_fallback")
        self.assertTrue(summary["symbols"][0]["partial"])

    def test_build_market_dataset_intraday_bypasses_daily_cache(self) -> None:
        fake_yf = _FakeYFinance(_make_intraday_frame())
        universe = get_market_monitor_universe()

        with patch("tradingagents.web.market_monitor.data.get_yf", return_value=fake_yf), patch(
            "tradingagents.web.market_monitor.data.evaluate_symbol_daily_cache"
        ) as cache_mock, patch("tradingagents.web.market_monitor.data.save_symbol_daily_cache") as save_mock:
            dataset = build_market_dataset(universe, date(2026, 4, 10), data_mode="intraday_delayed", include_event_news=False)

        self.assertEqual(dataset["data_mode"], "intraday_delayed")
        self.assertEqual(dataset["cache_summary"]["interval"], "5m")
        cache_mock.assert_not_called()
        save_mock.assert_not_called()

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
