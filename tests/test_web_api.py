import shutil
import time
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolCall, ToolMessage

from tradingagents.web.app import app, job_manager
from tradingagents.web.job_manager import AnalysisJobManager


class DummyPropagator:
    def create_initial_state(self, company_name, trade_date):
        return {
            "messages": [("human", company_name)],
            "company_of_interest": company_name,
            "trade_date": trade_date,
        }

    def get_graph_args(self, callbacks=None):
        return {"stream_mode": "values", "config": {}}


class DummyCompiledGraph:
    def __init__(self, final_state):
        self.final_state = final_state

    def stream(self, init_agent_state, **kwargs):
        yield {
            **init_agent_state,
            "messages": [HumanMessage(content=init_agent_state["company_of_interest"])],
        }
        yield {
            **init_agent_state,
            "messages": [
                AIMessage(
                    content="Collecting market data",
                    tool_calls=[
                        ToolCall(
                            name="get_stock_data",
                            args={"symbol": init_agent_state["company_of_interest"]},
                            id="tool-call-1",
                        )
                    ],
                )
            ],
        }
        yield {
            **init_agent_state,
            "messages": [
                ToolMessage(
                    content="market payload",
                    tool_call_id="tool-call-1",
                )
            ],
            "market_report": "Market report",
        }
        yield self.final_state


class DummyTradingAgentsGraph:
    def __init__(self, selected_analysts, debug, config):
        self.selected_analysts = selected_analysts
        self.debug = debug
        self.config = config
        self.ticker = None
        self.curr_state = None
        self.propagator = DummyPropagator()
        self._final_state = {
            "company_of_interest": "NVDA",
            "trade_date": date.today().isoformat(),
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
            "messages": [AIMessage(content="Final decision ready")],
        }
        self.graph = DummyCompiledGraph(self._final_state)

    def propagate(self, company_name, trade_date):
        return self._final_state, "BUY"

    def _log_state(self, trade_date, final_state):
        self.curr_state = final_state
        self.ticker = final_state["company_of_interest"]

    def process_signal(self, full_signal):
        return str(full_signal).strip()


class FailingCompiledGraph:
    def stream(self, init_agent_state, **kwargs):
        raise RuntimeError(
            f"boom for {init_agent_state['company_of_interest']} "
            f"on {init_agent_state['trade_date']}"
        )


class FailingTradingAgentsGraph:
    def __init__(self, selected_analysts, debug, config):
        self.selected_analysts = selected_analysts
        self.debug = debug
        self.config = config
        self.propagator = DummyPropagator()
        self.graph = FailingCompiledGraph()

    def propagate(self, company_name, trade_date):
        raise RuntimeError(f"boom for {company_name} on {trade_date}")


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

    def _wait_for_status(self, job_id, expected_status):
        detail = None
        for _ in range(30):
            response = self.client.get(f"/api/analysis-jobs/{job_id}")
            self.assertEqual(response.status_code, 200)
            detail = response.json()
            if detail["status"] == expected_status:
                return detail
            time.sleep(0.1)
        self.fail(f"job {job_id} did not reach status {expected_status}: {detail}")

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
                    "backend_url": "https://api.openai.com/v1",
                    "openai_reasoning_effort": "high",
                    "output_language": "English",
                    "max_debate_rounds": 5,
                    "max_risk_discuss_rounds": 5,
                    "max_recur_limit": 120,
                },
            )

            self.assertEqual(create_response.status_code, 200)
            job_id = create_response.json()["job_id"]

            detail = self._wait_for_status(job_id, "completed")
            self.assertEqual(detail["request"]["ticker"], "NVDA")
            self.assertEqual(
                detail["request"]["selected_analysts"],
                ["market", "news"],
            )
            self.assertEqual(
                detail["request"]["backend_url"],
                "https://api.openai.com/v1",
            )
            self.assertEqual(
                detail["request"]["openai_reasoning_effort"],
                "high",
            )
            self.assertEqual(detail["request"]["output_language"], "English")
            self.assertEqual(detail["request"]["max_debate_rounds"], 5)
            self.assertEqual(detail["request"]["max_risk_discuss_rounds"], 5)
            self.assertEqual(detail["request"]["max_recur_limit"], 120)
            self.assertEqual(detail["decision"], "BUY")
            self.assertEqual(detail["final_state"]["market_report"], "Market report")
            self.assertTrue(str(detail["log_path"]).endswith(f"{job_id}\\message_tool.log") or str(detail["log_path"]).endswith(f"{job_id}/message_tool.log"))

            log_text = Path(detail["log_path"]).read_text(encoding="utf-8")
            self.assertIn("[Agent] Collecting market data", log_text)
            self.assertIn("[Tool Call] get_stock_data(symbol=NVDA)", log_text)
            self.assertIn("[Data] market payload", log_text)

            report_response = self.client.get(f"/api/analysis-jobs/{job_id}/report")
            self.assertEqual(report_response.status_code, 200)
            self.assertIn("Trading Analysis Report: NVDA", report_response.text)

            history_response = self.client.get("/api/historical-reports")
            self.assertEqual(history_response.status_code, 200)
            history_payload = history_response.json()
            self.assertGreaterEqual(len(history_payload), 1)
            self.assertEqual(history_payload[0]["job_id"], job_id)
            self.assertEqual(history_payload[0]["ticker"], "NVDA")
            self.assertEqual(
                history_payload[0]["backend_url"],
                "https://api.openai.com/v1",
            )
            self.assertEqual(
                history_payload[0]["openai_reasoning_effort"],
                "high",
            )
            self.assertEqual(history_payload[0]["output_language"], "English")
            self.assertEqual(history_payload[0]["max_debate_rounds"], 5)
            self.assertEqual(history_payload[0]["max_risk_discuss_rounds"], 5)
            self.assertEqual(history_payload[0]["max_recur_limit"], 120)

            detail_response = self.client.get(f"/api/historical-reports/{job_id}")
            self.assertEqual(detail_response.status_code, 200)
            detail_payload = detail_response.json()
            self.assertEqual(detail_payload["job_id"], job_id)
            self.assertEqual(detail_payload["output_language"], "English")
            self.assertEqual(detail_payload["openai_reasoning_effort"], "high")
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

    def test_selected_analysts_are_normalized_and_same_day_jobs_are_isolated(self):
        with patch(
            "tradingagents.web.job_manager.TradingAgentsGraph",
            DummyTradingAgentsGraph,
        ):
            payload = {
                "ticker": "aapl",
                "trade_date": date.today().isoformat(),
                "selected_analysts": ["news", "market"],
                "llm_provider": "openai",
                "deep_think_llm": "gpt-5.4",
                "quick_think_llm": "gpt-5.4-mini",
            }
            first_job_id = self.client.post("/api/analysis-jobs", json=payload).json()[
                "job_id"
            ]
            second_job_id = self.client.post("/api/analysis-jobs", json=payload).json()[
                "job_id"
            ]

            first_detail = self._wait_for_status(first_job_id, "completed")
            second_detail = self._wait_for_status(second_job_id, "completed")

            self.assertEqual(
                first_detail["request"]["selected_analysts"],
                ["market", "news"],
            )
            self.assertNotEqual(first_detail["report_path"], second_detail["report_path"])
            self.assertNotEqual(first_detail["log_path"], second_detail["log_path"])
            self.assertIn(first_job_id, first_detail["report_path"])
            self.assertIn(second_job_id, second_detail["report_path"])

    def test_failed_job_persists_log_and_snapshot(self):
        with patch(
            "tradingagents.web.job_manager.TradingAgentsGraph",
            FailingTradingAgentsGraph,
        ):
            create_response = self.client.post(
                "/api/analysis-jobs",
                json={
                    "ticker": "msft",
                    "trade_date": date.today().isoformat(),
                    "selected_analysts": ["market"],
                    "llm_provider": "openai",
                    "deep_think_llm": "gpt-5.4",
                    "quick_think_llm": "gpt-5.4-mini",
                },
            )

            self.assertEqual(create_response.status_code, 200)
            job_id = create_response.json()["job_id"]

            detail = self._wait_for_status(job_id, "failed")
            self.assertIn("boom for MSFT", detail["error_message"])
            self.assertTrue(detail["log_path"])

            log_path = Path(detail["log_path"])
            snapshot_path = log_path.parent / "job_snapshot.json"
            self.assertTrue(log_path.exists())
            self.assertTrue(snapshot_path.exists())
            log_text = log_path.read_text(encoding="utf-8")
            self.assertIn("Job", log_text)
            self.assertIn("RuntimeError: boom for MSFT", log_text)


if __name__ == "__main__":
    unittest.main()
