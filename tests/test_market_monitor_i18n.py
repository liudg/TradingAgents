import unittest
from datetime import date, timedelta

from pydantic import ValidationError

from tradingagents.web.market_monitor.schemas import MarketMonitorSnapshotRequest


class MarketMonitorI18nTests(unittest.TestCase):
    def test_future_as_of_date_uses_chinese_validation_message(self) -> None:
        tomorrow = date.today() + timedelta(days=1)

        with self.assertRaises(ValidationError) as context:
            MarketMonitorSnapshotRequest(as_of_date=tomorrow)

        self.assertIn("as_of_date 不能晚于今天", str(context.exception))


if __name__ == "__main__":
    unittest.main()
