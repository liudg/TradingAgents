import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tradingagents.web.market_monitor.errors import MarketMonitorError, MarketMonitorNotFoundError
from tradingagents.web.market_monitor.trace import MarketMonitorTraceStore


class MarketMonitorTraceStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="market-monitor-trace-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_trace_module_round_trip_works(self) -> None:
        store = MarketMonitorTraceStore(trace_root=self.temp_dir)
        logger = store.create_logger(date(2026, 4, 12), force_refresh=True)
        logger.set_stage("request", {"as_of_date": "2026-04-12"})
        logger.set_stage("cache_decision", {"snapshot_cache_hit": False})
        logger.log_event("Request", "启动市场监控")
        logger.complete({"trace_id": logger.trace_id})

        traces = store.list_traces(as_of_date=date(2026, 4, 12))
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].trace_id, logger.trace_id)
        self.assertTrue(traces[0].force_refresh)

        detail = store.get_trace_detail(logger.trace_id)
        self.assertEqual(detail.request["as_of_date"], "2026-04-12")
        self.assertEqual(detail.response_summary["trace_id"], logger.trace_id)

        logs = store.list_trace_logs(logger.trace_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].level, "Request")
        self.assertIn("启动市场监控", logs[0].content)

    def test_trace_store_uses_market_monitor_exceptions(self) -> None:
        store = MarketMonitorTraceStore(trace_root=self.temp_dir)

        with self.assertRaises(MarketMonitorNotFoundError):
            store.get_trace_detail("missing-trace")

        logger = store.create_logger(date(2026, 4, 12), force_refresh=False)
        snapshot_path = logger.snapshot_path
        snapshot_path.write_text("not-json", encoding="utf-8")

        with self.assertRaises(MarketMonitorError):
            store.get_trace_detail(logger.trace_id)


if __name__ == "__main__":
    unittest.main()
