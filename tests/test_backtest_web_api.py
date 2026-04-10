import shutil
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.web.api.app import app, backtest_manager
from tradingagents.web.backtest.manager import BacktestJobManager


class DummyBacktestLLM:
    def invoke(self, prompt):
        class Response:
            content = (
                '{"decision_quality":"strong","key_success_factors":"Aligned evidence.",'
                '"key_failure_factors":"None","what_should_change":"Keep filtering noisy setups.",'
                '"reusable_rule":"Favor aligned multi-agent signals with controlled drawdown.",'
                '"memory_query":"aligned buy setup","confidence":"high"}'
            )

        return Response()


class DummyBacktestGraph:
    def __init__(self, selected_analysts, debug, config):
        self.selected_analysts = selected_analysts
        self.debug = debug
        self.config = config
        self.quick_thinking_llm = DummyBacktestLLM()

    def propagate(self, company_name, trade_date):
        day = int(str(trade_date).split("-")[-1])
        signal = "BUY" if day % 2 else "HOLD"
        final_state = {
            "company_of_interest": company_name,
            "trade_date": trade_date,
            "market_report": f"Market report {trade_date}",
            "sentiment_report": f"Sentiment report {trade_date}",
            "news_report": f"News report {trade_date}",
            "fundamentals_report": f"Fundamentals report {trade_date}",
            "investment_plan": f"Investment plan {trade_date}",
            "trader_investment_plan": f"Trader plan {trade_date}",
            "final_trade_decision": signal,
            "investment_debate_state": {
                "bull_history": "Bull thesis",
                "bear_history": "Bear thesis",
                "history": "History",
                "current_response": "Current",
                "judge_decision": "Judge",
            },
            "risk_debate_state": {
                "aggressive_history": "Aggressive",
                "conservative_history": "Conservative",
                "neutral_history": "Neutral",
                "history": "Risk history",
                "judge_decision": "Portfolio",
            },
        }
        return final_state, signal


class BacktestWebApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.temp_dir = Path.cwd() / "reports" / "backtest_web_api_tests" / str(time.time_ns())
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.original_backtests_root = backtest_manager.backtests_root
        self.original_memory_dir = DEFAULT_CONFIG["memory_dir"]
        backtest_manager.backtests_root = self.temp_dir
        DEFAULT_CONFIG["memory_dir"] = str(self.temp_dir / "memory")

    def tearDown(self):
        backtest_manager.backtests_root = self.original_backtests_root
        DEFAULT_CONFIG["memory_dir"] = self.original_memory_dir
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _wait_for_status(self, job_id, expected_status):
        detail = None
        for _ in range(40):
            response = self.client.get(f"/api/backtest-jobs/{job_id}")
            self.assertEqual(response.status_code, 200)
            detail = response.json()
            if detail["status"] == expected_status:
                return detail
            time.sleep(0.1)
        self.fail(f"job {job_id} did not reach status {expected_status}: {detail}")

    @staticmethod
    def _price_frame():
        dates = pd.date_range("2024-01-02", periods=8, freq="B")
        return pd.DataFrame(
            {
                "Date": dates,
                "Open": [100, 101, 103, 102, 104, 105, 106, 108],
                "High": [101, 103, 104, 103, 105, 107, 108, 110],
                "Low": [99, 100, 101, 100, 103, 104, 105, 107],
                "Close": [100, 102, 102, 103, 105, 106, 107, 109],
                "DateOnly": [item.date() for item in dates],
            }
        )

    def test_create_and_restore_backtest_job(self):
        add_calls = []

        def fake_add_situations(self, situations_and_advice):
            add_calls.append(list(situations_and_advice))

        with patch(
            "tradingagents.web.backtest.manager.TradingAgentsGraph",
            DummyBacktestGraph,
        ), patch(
            "tradingagents.web.backtest.manager.BacktestJobManager._fetch_price_history",
            return_value=self._price_frame(),
        ), patch(
            "tradingagents.agents.utils.memory.FinancialSituationMemory.add_situations",
            new=fake_add_situations,
        ):
            create_response = self.client.post(
                "/api/backtest-jobs",
                json={
                    "ticker": "nvda",
                    "start_date": "2024-01-02",
                    "end_date": "2024-01-05",
                    "selected_analysts": ["market", "news"],
                    "llm_provider": "openai",
                    "deep_think_llm": "gpt-5.4",
                    "quick_think_llm": "gpt-5.4-mini",
                    "holding_period": 2,
                    "reflection_enabled": True,
                    "writeback_enabled": True,
                },
            )

            self.assertEqual(create_response.status_code, 200)
            job_id = create_response.json()["job_id"]
            detail = self._wait_for_status(job_id, "completed")
            self.assertEqual(detail["request"]["ticker"], "NVDA")
            self.assertEqual(detail["summary"]["sample_count"], 4)
            self.assertEqual(detail["summary"]["evaluated_count"], 4)
            self.assertGreaterEqual(detail["summary"]["reflection_count"], 1)
            self.assertGreaterEqual(detail["summary"]["memory_write_count"], 1)
            self.assertEqual(detail["stage"], "completed")
            self.assertEqual(detail["memory_commit_status"], "committed")
            self.assertGreaterEqual(len(detail["samples"]), 4)
            self.assertTrue(detail["memory_entries"])
            self.assertEqual(len(add_calls), 1)
            self.assertEqual(len(add_calls[0]), detail["summary"]["memory_write_count"])
            written_dates = {entry["trade_date"] for entry in detail["memory_entries"]}
            for sample in detail["samples"]:
                self.assertEqual(sample["memory_written"], sample["trade_date"] in written_dates)

            logs_response = self.client.get(f"/api/backtest-jobs/{job_id}/logs")
            self.assertEqual(logs_response.status_code, 200)
            self.assertTrue(any("Evaluating historical decisions" in item["content"] for item in logs_response.json()))
            self.assertTrue(any("Committing" in item["content"] for item in logs_response.json()))

            history_response = self.client.get("/api/historical-backtests")
            self.assertEqual(history_response.status_code, 200)
            history_payload = history_response.json()
            self.assertEqual(history_payload[0]["job_id"], job_id)
            self.assertEqual(history_payload[0]["holding_period"], 2)
            self.assertEqual(history_payload[0]["memory_commit_status"], "committed")

            detail_response = self.client.get(f"/api/historical-backtests/{job_id}")
            self.assertEqual(detail_response.status_code, 200)
            detail_payload = detail_response.json()
            self.assertEqual(detail_payload["summary"]["sample_count"], 4)
            self.assertTrue(detail_payload["memory_entries"])

            restored_manager = BacktestJobManager(
                backtests_root=self.temp_dir,
                max_workers=1,
            )
            restored_history = restored_manager.list_historical_backtests()
            self.assertEqual(len(restored_history), 1)
            restored_detail = restored_manager.get_historical_backtest(job_id)
            self.assertEqual(restored_detail.summary.sample_count, 4)
            self.assertEqual(restored_detail.memory_commit_status, "committed")

    def test_failed_backtest_does_not_commit_memory(self):
        add_calls = []

        def fake_add_situations(self, situations_and_advice):
            add_calls.append(list(situations_and_advice))

        with patch(
            "tradingagents.web.backtest.manager.TradingAgentsGraph",
            DummyBacktestGraph,
        ), patch(
            "tradingagents.web.backtest.manager.BacktestJobManager._fetch_price_history",
            return_value=self._price_frame(),
        ), patch(
            "tradingagents.agents.utils.memory.FinancialSituationMemory.add_situations",
            new=fake_add_situations,
        ), patch(
            "tradingagents.web.backtest.manager.BacktestJobManager._commit_memory_entries",
            side_effect=RuntimeError("commit failed"),
        ):
            create_response = self.client.post(
                "/api/backtest-jobs",
                json={
                    "ticker": "nvda",
                    "start_date": "2024-01-02",
                    "end_date": "2024-01-05",
                    "selected_analysts": ["market", "news"],
                    "llm_provider": "openai",
                    "deep_think_llm": "gpt-5.4",
                    "quick_think_llm": "gpt-5.4-mini",
                    "holding_period": 2,
                    "reflection_enabled": True,
                    "writeback_enabled": True,
                },
            )

            self.assertEqual(create_response.status_code, 200)
            job_id = create_response.json()["job_id"]
            detail = self._wait_for_status(job_id, "failed")
            self.assertEqual(detail["memory_commit_status"], "skipped_due_to_failure")
            self.assertTrue(detail["memory_entries"])
            self.assertFalse(add_calls)
            self.assertTrue(all(not sample["memory_written"] for sample in detail["samples"]))

            logs_response = self.client.get(f"/api/backtest-jobs/{job_id}/logs")
            self.assertEqual(logs_response.status_code, 200)
            self.assertTrue(
                any("Memory commit skipped because the backtest job failed" in item["content"] for item in logs_response.json())
            )


if __name__ == "__main__":
    unittest.main()
