import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_CLI_PATH = PROJECT_ROOT / "skill-cli" / "tradingagents_skill.py"


def load_skill_cli_module():
    spec = importlib.util.spec_from_file_location("tradingagents_skill_cli_under_test", SKILL_CLI_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SkillCliTests(unittest.TestCase):
    def setUp(self):
        self.skill_cli = load_skill_cli_module()

    def test_validate_ticker_accepts_allowed_formats(self):
        for ticker in ("AAPL", "BRK-B", "BRK.A", "0700.HK", "ABC_1"):
            self.assertEqual(self.skill_cli.validate_ticker(ticker), ticker)

    def test_validate_ticker_rejects_unsafe_values(self):
        for ticker in ("", "aapl", "AAP L", "../AAPL", "AAPL/US", "AAPL\\US", "A" * 33):
            with self.assertRaises(self.skill_cli.ArgumentError):
                self.skill_cli.validate_ticker(ticker)

    def test_main_writes_only_markdown_to_stdout_on_success(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch.object(self.skill_cli, "run_stock_analysis", return_value="**Rating**: Buy"):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = self.skill_cli.main(["stock-analysis", "AAPL"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "**Rating**: Buy\n")
        self.assertEqual(stderr.getvalue(), "")

    def test_main_returns_argument_error_without_stdout(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exit_code = self.skill_cli.main(["stock-analysis", "../AAPL"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("参数错误", stderr.getvalue())

    def test_subprocess_success_outputs_only_markdown_to_stdout(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_project = Path(temp_dir)
            fake_skill_dir = fake_project / "skill-cli"
            fake_graph_dir = fake_project / "tradingagents" / "graph"
            fake_skill_dir.mkdir(parents=True)
            fake_graph_dir.mkdir(parents=True)
            shutil.copyfile(SKILL_CLI_PATH, fake_skill_dir / "tradingagents_skill.py")
            (fake_project / "tradingagents" / "__init__.py").write_text("", encoding="utf-8")
            (fake_graph_dir / "__init__.py").write_text("", encoding="utf-8")
            fake_dataflows_dir = fake_project / "tradingagents" / "dataflows"
            fake_dataflows_dir.mkdir(parents=True)
            (fake_dataflows_dir / "__init__.py").write_text("", encoding="utf-8")
            (fake_dataflows_dir / "utils.py").write_text(
                "def safe_ticker_component(ticker):\n    return ticker\n",
                encoding="utf-8",
            )
            (fake_project / "tradingagents" / "reporting.py").write_text(
                textwrap.dedent(
                    """
                    def save_report_to_disk(final_state, ticker, save_path):
                        save_path.mkdir(parents=True, exist_ok=True)
                        report_path = save_path / "complete_report.md"
                        report_path.write_text(final_state["final_trade_decision"], encoding="utf-8")
                        return report_path
                    """
                ),
                encoding="utf-8",
            )
            (fake_project / "tradingagents" / "default_config.py").write_text(
                f"DEFAULT_CONFIG = {{'checkpoint_enabled': True, 'data_cache_dir': 'cache', 'results_dir': {str(fake_project / 'logs')!r}}}\n",
                encoding="utf-8",
            )
            (fake_graph_dir / "trading_graph.py").write_text(
                textwrap.dedent(
                    """
                    class TradingAgentsGraph:
                        def __init__(self, selected_analysts, debug, config):
                            self.config = config

                        def propagate(self, ticker, trade_date):
                            print(f"progress for {ticker} on {trade_date}")
                            return {"final_trade_decision": "# Final Decision\\nBuy"}, "Buy"
                    """
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(fake_skill_dir / "tradingagents_skill.py"),
                    "stock-analysis",
                    "AAPL",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env={
                    **os.environ,
                    "PYTHONUTF8": "1",
                    "PYTHONIOENCODING": "utf-8",
                },
                check=False,
            )

            reports = list((fake_project / "logs" / "AAPL").rglob("reports/complete_report.md"))
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0].read_text(encoding="utf-8"), "# Final Decision\nBuy")
            job_dir = reports[0].parent.parent
            self.assertTrue((job_dir / "job_snapshot.json").is_file())
            self.assertTrue((job_dir / "message_tool.log").is_file())
            snapshot = json.loads((job_dir / "job_snapshot.json").read_text(encoding="utf-8"))
            self.assertEqual(snapshot["status"], "completed")
            self.assertEqual(snapshot["request"]["ticker"], "AAPL")
            self.assertEqual(snapshot["report_path"], str(reports[0]))

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "# Final Decision\nBuy\n")
            self.assertIn("progress for AAPL", result.stderr)
            self.assertIn("完整报告已保存:", result.stderr)

    def test_run_stock_analysis_redirects_internal_stdout_to_stderr(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        results_dir = Path(temp_dir.name) / "logs"

        default_config_module = types.ModuleType("tradingagents.default_config")
        default_config_module.DEFAULT_CONFIG = {
            "checkpoint_enabled": True,
            "data_cache_dir": "cache",
            "results_dir": str(results_dir),
        }

        graph_module = types.ModuleType("tradingagents.graph.trading_graph")
        dataflows_utils_module = types.ModuleType("tradingagents.dataflows.utils")
        reporting_module = types.ModuleType("tradingagents.reporting")

        calls = []
        saved_reports = []

        class FakeTradingAgentsGraph:
            def __init__(self, selected_analysts, debug, config):
                self.selected_analysts = selected_analysts
                self.debug = debug
                self.config = config

            def propagate(self, ticker, trade_date):
                print(f"progress for {ticker} on {trade_date}")
                calls.append((ticker, trade_date, self.config["checkpoint_enabled"]))
                return {"final_trade_decision": "# 最终结论\n买入"}, "Buy"

        graph_module.TradingAgentsGraph = FakeTradingAgentsGraph

        def safe_ticker_component(ticker):
            return ticker

        def save_report_to_disk(final_state, ticker, save_path):
            save_path.mkdir(parents=True, exist_ok=True)
            report_path = save_path / "complete_report.md"
            report_path.write_text(final_state["final_trade_decision"], encoding="utf-8")
            saved_reports.append((ticker, report_path))
            return report_path

        dataflows_utils_module.safe_ticker_component = safe_ticker_component
        reporting_module.save_report_to_disk = save_report_to_disk

        tradingagents_module = types.ModuleType("tradingagents")
        tradingagents_module.__path__ = []
        graph_package = types.ModuleType("tradingagents.graph")
        graph_package.__path__ = []
        dataflows_package = types.ModuleType("tradingagents.dataflows")
        dataflows_package.__path__ = []

        stdout = io.StringIO()
        stderr = io.StringIO()
        fake_modules = {
            "tradingagents": tradingagents_module,
            "tradingagents.default_config": default_config_module,
            "tradingagents.graph": graph_package,
            "tradingagents.graph.trading_graph": graph_module,
            "tradingagents.dataflows": dataflows_package,
            "tradingagents.dataflows.utils": dataflows_utils_module,
            "tradingagents.reporting": reporting_module,
        }

        with patch.dict(sys.modules, fake_modules):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                markdown = self.skill_cli.run_stock_analysis("AAPL")

        self.assertEqual(markdown, "# 最终结论\n买入")
        self.assertEqual(calls[0][0], "AAPL")
        self.assertFalse(calls[0][2])
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("progress for AAPL", stderr.getvalue())
        self.assertIn("完整报告已保存:", stderr.getvalue())
        self.assertEqual(saved_reports[0][0], "AAPL")
        self.assertTrue(saved_reports[0][1].is_file())
        job_dir = saved_reports[0][1].parent.parent
        self.assertTrue((job_dir / "job_snapshot.json").is_file())
        self.assertTrue((job_dir / "message_tool.log").is_file())
        self.assertEqual(
            saved_reports[0][1].relative_to(results_dir).parts[:2],
            ("AAPL", calls[0][1]),
        )


if __name__ == "__main__":
    unittest.main()
