import os
import tempfile
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import yfinance as yf

from tradingagents.dataflows import stockstats_utils, yfinance_news
from tradingagents.dataflows.yfinance_proxy import configure_yfinance_proxy
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.web.backtest.manager import BacktestJobManager


class YFinanceProxyConfigTests(unittest.TestCase):
    def tearDown(self):
        for key in ("YFINANCE_PROXY", "YFINANCE_HTTP_PROXY", "YFINANCE_HTTPS_PROXY"):
            os.environ.pop(key, None)
        yf.config.network.proxy = None

    def test_single_proxy_populates_both_schemes(self):
        os.environ["YFINANCE_PROXY"] = "socks5h://127.0.0.1:7897"

        configure_yfinance_proxy()

        self.assertEqual(
            yf.config.network.proxy,
            {
                "http": "socks5h://127.0.0.1:7897",
                "https": "socks5h://127.0.0.1:7897",
            },
        )

    def test_scheme_specific_proxy_falls_back_to_other_scheme(self):
        os.environ["YFINANCE_HTTPS_PROXY"] = "socks5h://127.0.0.1:7897"

        configure_yfinance_proxy()

        self.assertEqual(
            yf.config.network.proxy,
            {
                "http": "socks5h://127.0.0.1:7897",
                "https": "socks5h://127.0.0.1:7897",
            },
        )

    def test_load_ohlcv_configures_proxy_before_download(self):
        frame = pd.DataFrame(
            {
                "Open": [1.0],
                "High": [2.0],
                "Low": [0.5],
                "Close": [1.5],
                "Volume": [100],
            },
            index=pd.to_datetime(["2024-01-02"]),
        )
        frame.index.name = "Date"
        yf_mock = MagicMock()
        yf_mock.download.return_value = frame

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(stockstats_utils, "get_yf", return_value=yf_mock) as get_yf_mock:
                with patch.object(stockstats_utils, "get_config", return_value={"data_cache_dir": temp_dir}):
                    with patch.object(stockstats_utils.os.path, "exists", return_value=False):
                        data = stockstats_utils.load_ohlcv("AAPL", "2024-01-03")

        get_yf_mock.assert_called_once_with()
        self.assertFalse(data.empty)

    def test_get_news_yfinance_configures_proxy_before_ticker_request(self):
        ticker_mock = MagicMock()
        ticker_mock.get_news.return_value = []

        with patch.object(yfinance_news.yf, "Ticker", return_value=ticker_mock) as ticker_cls:
            result = yfinance_news.get_news_yfinance("AAPL", "2024-01-01", "2024-01-02")

        ticker_cls.assert_called_once_with("AAPL")
        self.assertIn("No news found for AAPL", result)

    def test_get_global_news_yfinance_configures_proxy_before_search_request(self):
        search_mock = MagicMock()
        search_mock.news = []

        with patch.object(yfinance_news.yf, "Search", return_value=search_mock) as search_cls:
            result = yfinance_news.get_global_news_yfinance("2024-01-02")

        search_cls.assert_called()
        self.assertIn("No global news found", result)

    def test_backtest_history_download_configures_proxy(self):
        frame = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2024-01-02"]),
                "Open": [1.0],
                "Close": [1.5],
            }
        )

        yf_mock = MagicMock()
        yf_mock.download.return_value = frame

        with patch("tradingagents.web.backtest.manager.get_yf", return_value=yf_mock) as get_yf_mock:
            data = BacktestJobManager._fetch_price_history(
                "AAPL",
                date(2024, 1, 1),
                date(2024, 1, 3),
            )

        get_yf_mock.assert_called_once_with()
        self.assertFalse(data.empty)

    def test_fetch_returns_uses_proxy_for_history(self):
        stock_frame = pd.DataFrame({"Close": [100.0, 102.0, 104.0, 106.0]})
        spy_frame = pd.DataFrame({"Close": [400.0, 402.0, 404.0, 406.0]})
        def make_ticker(symbol):
            ticker = MagicMock()
            ticker.history.return_value = spy_frame if symbol == "SPY" else stock_frame
            return ticker

        with patch("tradingagents.graph.trading_graph.yf.Ticker", side_effect=make_ticker) as ticker_cls:
            raw, alpha, days = TradingAgentsGraph._fetch_returns(
                MagicMock(spec=TradingAgentsGraph),
                "AAPL",
                "2024-01-02",
            )

        self.assertEqual(ticker_cls.call_count, 2)
        self.assertIsNotNone(raw)
        self.assertIsNotNone(alpha)
        self.assertEqual(days, 3)


if __name__ == "__main__":
    unittest.main()
