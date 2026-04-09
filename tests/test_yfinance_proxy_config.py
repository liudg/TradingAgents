import os
import unittest

import yfinance as yf

from tradingagents.dataflows.y_finance import _configure_yfinance_proxy


class YFinanceProxyConfigTests(unittest.TestCase):
    def tearDown(self):
        for key in ("YFINANCE_PROXY", "YFINANCE_HTTP_PROXY", "YFINANCE_HTTPS_PROXY"):
            os.environ.pop(key, None)
        yf.config.network.proxy = None

    def test_single_proxy_populates_both_schemes(self):
        os.environ["YFINANCE_PROXY"] = "socks5h://127.0.0.1:7897"

        _configure_yfinance_proxy()

        self.assertEqual(
            yf.config.network.proxy,
            {
                "http": "socks5h://127.0.0.1:7897",
                "https": "socks5h://127.0.0.1:7897",
            },
        )

    def test_scheme_specific_proxy_falls_back_to_other_scheme(self):
        os.environ["YFINANCE_HTTPS_PROXY"] = "socks5h://127.0.0.1:7897"

        _configure_yfinance_proxy()

        self.assertEqual(
            yf.config.network.proxy,
            {
                "http": "socks5h://127.0.0.1:7897",
                "https": "socks5h://127.0.0.1:7897",
            },
        )


if __name__ == "__main__":
    unittest.main()
