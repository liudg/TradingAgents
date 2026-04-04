import sys
import types
import unittest

import pandas as pd

from tradingagents.dataflows.futu import _normalize_futu_code, get_stock


class FakeQuoteContext:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.closed = False

    def request_history_kline(
        self,
        code,
        start=None,
        end=None,
        ktype=None,
        autype=None,
        fields=None,
        max_count=1000,
        page_req_key=None,
        session=None,
    ):
        data = pd.DataFrame(
            [
                {
                    "code": code,
                    "name": "Apple",
                    "time_key": "2024-05-10 00:00:00",
                    "open": 184.9,
                    "close": 183.05,
                    "high": 185.09,
                    "low": 182.13,
                    "volume": 50759500,
                }
            ]
        )
        return 0, data, None

    def close(self):
        self.closed = True


class FutuVendorTests(unittest.TestCase):
    def setUp(self):
        self.original_futu = sys.modules.get("futu")
        fake_futu = types.SimpleNamespace(
            OpenQuoteContext=FakeQuoteContext,
            RET_OK=0,
            KLType=types.SimpleNamespace(K_DAY="K_DAY"),
            AuType=types.SimpleNamespace(QFQ="QFQ"),
            KL_FIELD=types.SimpleNamespace(ALL="ALL"),
            Session=types.SimpleNamespace(ALL="ALL", NONE="NONE"),
        )
        sys.modules["futu"] = fake_futu

    def tearDown(self):
        if self.original_futu is None:
            sys.modules.pop("futu", None)
        else:
            sys.modules["futu"] = self.original_futu

    def test_normalize_futu_code(self):
        self.assertEqual(_normalize_futu_code("AAPL"), "US.AAPL")
        self.assertEqual(_normalize_futu_code("0700.HK"), "HK.00700")
        self.assertEqual(_normalize_futu_code("600519.SS"), "SH.600519")
        self.assertEqual(_normalize_futu_code("000001.SZ"), "SZ.000001")
        self.assertEqual(_normalize_futu_code("HK.00700"), "HK.00700")
        self.assertEqual(_normalize_futu_code("BRK.B"), "US.BRK.B")

    def test_normalize_futu_code_rejects_unsupported_exchange_suffix(self):
        with self.assertRaises(ValueError):
            _normalize_futu_code("7203.T")

    def test_get_stock_uses_futu_and_returns_csv_payload(self):
        result = get_stock("AAPL", "2024-05-01", "2024-05-31")

        self.assertIn("# Source: Futu OpenAPI", result)
        self.assertIn("2024-05-10", result)
        self.assertIn("183.05", result)


if __name__ == "__main__":
    unittest.main()
