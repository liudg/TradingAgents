import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.data import _download_single_symbol


class _FakeYFinance:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def download(self, **kwargs):
        self.calls.append(kwargs)
        return pd.DataFrame()


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


if __name__ == "__main__":
    unittest.main()
