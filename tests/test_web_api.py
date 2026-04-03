import shutil
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from tradingagents.web.app import app, job_manager
from tradingagents.web.job_manager import AnalysisJobManager


class DummyTradingAgentsGraph:
    def __init__(self, selected_analysts, debug, config):
        self.selected_analysts = selected_analysts
        self.debug = debug
        self.config = config

    def propagate(self, company_name, trade_date):
        return (
            {
                "company_of_interest": company_name,
                "trade_date": trade_date,
                "market_report": "Market report",
                "sentiment_report": "Sentiment report",
                "news_report": "News report",
                "fundamentals_report": "Fundamentals report",
                "investment_plan": "Investment plan",
                "trader_investment_plan": "Trader plan",
                "final_trade_decision": "BUY",
                "investment_debate_state": {
                    "bull_history": "Bull thesis",
                    "bear_history": "Bear thesis",
                    "history": "Debate history",
                    "current_response": "Latest response",
                    "judge_decision": "Research manager decision",
                },
                "risk_debate_state": {
                    "aggressive_history": "Aggressive",
                    "conservative_history": "Conservative",
                    "neutral_history": "Neutral",
                    "history": "Risk history",
                    "judge_decision": "Portfolio manager decision",
                },
            },
            "BUY",
        )


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.temp_dir = Path.cwd() / "reports" / "web_api_tests" / str(time.time_ns())
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.original_reports_root = job_manager.reports_root
        job_manager.reports_root = self.temp_dir

    def tearDown(self):
        job_manager.reports_root = self.original_reports_root
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_metadata_options_returns_models_and_defaults(self):
        response = self.client.get("/api/metadata/options")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("market", payload["analysts"])
        self.assertIn("openai", payload["llm_providers"])
        self.assertIn("models", payload)
        self.assertIn("default_config", payload)

    def test_unknown_job_returns_404(self):
        response = self.client.get("/api/analysis-jobs/not-exist")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Analysis job not found")

    def test_create_and_poll_job_until_completed(self):
        with patch(
            "tradingagents.web.job_manager.TradingAgentsGraph",
            DummyTradingAgentsGraph,
        ):
            create_response = self.client.post(
                "/api/analysis-jobs",
                json={
                    "ticker": "nvda",
                    "trade_date": date.today().isoformat(),
                    "selected_analysts": ["market", "news"],
                    "llm_provider": "openai",
                    "deep_think_llm": "gpt-5.4",
                    "quick_think_llm": "gpt-5.4-mini",
                },
            )

            self.assertEqual(create_response.status_code, 200)
            job_id = create_response.json()["job_id"]

            detail = None
            for _ in range(30):
                response = self.client.get(f"/api/analysis-jobs/{job_id}")
                self.assertEqual(response.status_code, 200)
                detail = response.json()
                if detail["status"] == "completed":
                    break
                time.sleep(0.1)

            self.assertIsNotNone(detail)
            self.assertEqual(detail["status"], "completed", detail)
            self.assertEqual(detail["request"]["ticker"], "NVDA")
            self.assertEqual(detail["decision"], "BUY")
            self.assertEqual(detail["final_state"]["market_report"], "Market report")

            report_response = self.client.get(f"/api/analysis-jobs/{job_id}/report")
            self.assertEqual(report_response.status_code, 200)
            self.assertIn("Trading Analysis Report: NVDA", report_response.text)

            history_response = self.client.get("/api/historical-reports")
            self.assertEqual(history_response.status_code, 200)
            history_payload = history_response.json()
            self.assertGreaterEqual(len(history_payload), 1)
            self.assertEqual(history_payload[0]["job_id"], job_id)
            self.assertEqual(history_payload[0]["ticker"], "NVDA")
            self.assertEqual(history_payload[0]["max_debate_rounds"], 1)

            detail_response = self.client.get(f"/api/historical-reports/{job_id}")
            self.assertEqual(detail_response.status_code, 200)
            detail_payload = detail_response.json()
            self.assertEqual(detail_payload["job_id"], job_id)
            self.assertGreaterEqual(len(detail_payload["agent_reports"]), 1)
            self.assertEqual(
                detail_payload["agent_reports"][0]["reports"][0]["content"],
                "Market report",
            )

            restored_manager = AnalysisJobManager(
                reports_root=self.temp_dir,
                max_workers=1,
            )
            restored_history = restored_manager.list_historical_reports()
            self.assertEqual(len(restored_history), 1)
            self.assertEqual(restored_history[0].job_id, job_id)
            restored_detail = restored_manager.get_historical_report(job_id)
            self.assertEqual(restored_detail.ticker, "NVDA")
            self.assertGreaterEqual(len(restored_detail.agent_reports), 1)


if __name__ == "__main__":
    unittest.main()
