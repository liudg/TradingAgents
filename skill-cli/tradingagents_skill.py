from __future__ import annotations

import contextlib
import copy
import io
import json
import logging
import re
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Sequence
from uuid import uuid4

EXIT_OK = 0
EXIT_ARGUMENT_ERROR = 2
EXIT_ENVIRONMENT_ERROR = 3
EXIT_ANALYSIS_FAILED = 4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TICKER_PATTERN = re.compile(r"^[A-Z0-9._-]{1,32}$")
DEFAULT_ANALYSTS = ["market", "social", "news", "fundamentals"]


class SkillCliError(Exception):
    exit_code = EXIT_ANALYSIS_FAILED


class ArgumentError(SkillCliError):
    exit_code = EXIT_ARGUMENT_ERROR


class SkillEnvironmentError(SkillCliError):
    exit_code = EXIT_ENVIRONMENT_ERROR


class AnalysisError(SkillCliError):
    exit_code = EXIT_ANALYSIS_FAILED


def _print_usage() -> None:
    print(
        "用法：python skill-cli/tradingagents_skill.py stock-analysis <ticker>",
        file=sys.stderr,
    )


def validate_ticker(ticker: str) -> str:
    if not TICKER_PATTERN.fullmatch(ticker):
        raise ArgumentError(
            "参数错误：ticker 只能包含 A-Z、0-9、点号、短横线、下划线，且长度必须为 1-32。"
        )
    return ticker


def _ensure_project_on_path() -> None:
    project_root = str(PROJECT_ROOT)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


def _load_project_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / ".env.enterprise", override=False)


def run_stock_analysis(ticker: str) -> str:
    _ensure_project_on_path()

    captured_stdout = io.StringIO()
    report_path: Path | None = None
    try:
        with contextlib.redirect_stdout(captured_stdout):
            _load_project_env()

            from tradingagents.default_config import DEFAULT_CONFIG
            from tradingagents.graph.trading_graph import TradingAgentsGraph

            config = copy.deepcopy(DEFAULT_CONFIG)
            config["checkpoint_enabled"] = False
            trade_date = date.today().isoformat()

            graph = TradingAgentsGraph(
                selected_analysts=DEFAULT_ANALYSTS,
                debug=False,
                config=config,
            )
            final_state, _decision = graph.propagate(ticker, trade_date)
            report_path = _save_complete_report(final_state, ticker, trade_date, config)
    except (ImportError, ModuleNotFoundError) as exc:
        _flush_captured_stdout(captured_stdout)
        raise SkillEnvironmentError(f"环境错误：无法加载项目依赖：{exc}") from exc
    except Exception as exc:
        _flush_captured_stdout(captured_stdout)
        raise AnalysisError(f"分析运行失败：{exc}") from exc

    _flush_captured_stdout(captured_stdout)

    markdown = final_state.get("final_trade_decision")
    if not isinstance(markdown, str) or not markdown.strip():
        raise AnalysisError("分析运行失败：未生成最终 Markdown 结论。")

    if report_path is not None:
        print(f"完整报告已保存: {report_path}", file=sys.stderr)

    return markdown.strip()


def _save_complete_report(
    final_state: dict,
    ticker: str,
    trade_date: str,
    config: dict,
) -> Path:
    from tradingagents.dataflows.utils import safe_ticker_component
    from tradingagents.reporting import save_report_to_disk

    safe_ticker = safe_ticker_component(ticker)
    job_id = uuid4().hex
    results_dir = Path(config["results_dir"]) / safe_ticker / trade_date / job_id
    report_path = save_report_to_disk(final_state, ticker, results_dir / "reports")
    _write_job_artifacts(
        results_dir=results_dir,
        job_id=job_id,
        ticker=ticker,
        trade_date=trade_date,
        final_state=final_state,
        config=config,
        report_path=report_path,
    )
    return report_path


def _write_job_artifacts(
    results_dir: Path,
    job_id: str,
    ticker: str,
    trade_date: str,
    final_state: dict,
    config: dict,
    report_path: Path,
) -> None:
    now = datetime.now()
    log_path = results_dir / "message_tool.log"
    log_path.write_text(
        "\n".join(
            [
                f"[{now.isoformat()}] System: skill-cli stock-analysis completed for {ticker}.",
                f"[{now.isoformat()}] System: Report saved to {report_path}.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = {
        "job_id": job_id,
        "status": "completed",
        "progress": 100,
        "request": _build_request_snapshot(ticker, trade_date, config),
        "final_state": _serialize_final_state(final_state),
        "decision": final_state.get("final_trade_decision"),
        "error_message": None,
        "report_path": str(report_path),
        "log_path": str(log_path),
        "results_dir": str(results_dir),
        "created_at": now.isoformat(),
        "started_at": now.isoformat(),
        "finished_at": now.isoformat(),
    }
    (results_dir / "job_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_request_snapshot(ticker: str, trade_date: str, config: dict) -> dict:
    return {
        "ticker": ticker,
        "trade_date": trade_date,
        "selected_analysts": DEFAULT_ANALYSTS,
        "llm_provider": config.get("llm_provider"),
        "deep_think_llm": config.get("deep_think_llm"),
        "quick_think_llm": config.get("quick_think_llm"),
        "backend_url": config.get("backend_url"),
        "google_thinking_level": config.get("google_thinking_level"),
        "openai_reasoning_effort": config.get("openai_reasoning_effort"),
        "codex_reasoning_effort": config.get("codex_reasoning_effort"),
        "anthropic_effort": config.get("anthropic_effort"),
        "output_language": config.get("output_language"),
        "max_debate_rounds": config.get("max_debate_rounds"),
        "max_risk_discuss_rounds": config.get("max_risk_discuss_rounds"),
    }


def _serialize_final_state(final_state: dict) -> dict:
    investment_debate_state = final_state.get("investment_debate_state") or {}
    risk_debate_state = final_state.get("risk_debate_state") or {}
    return {
        "company_of_interest": final_state.get("company_of_interest"),
        "trade_date": final_state.get("trade_date"),
        "market_report": final_state.get("market_report"),
        "sentiment_report": final_state.get("sentiment_report"),
        "news_report": final_state.get("news_report"),
        "fundamentals_report": final_state.get("fundamentals_report"),
        "investment_plan": final_state.get("investment_plan"),
        "trader_investment_plan": final_state.get("trader_investment_plan"),
        "final_trade_decision": final_state.get("final_trade_decision"),
        "investment_debate_state": {
            "bull_history": investment_debate_state.get("bull_history"),
            "bear_history": investment_debate_state.get("bear_history"),
            "history": investment_debate_state.get("history"),
            "current_response": investment_debate_state.get("current_response"),
            "judge_decision": investment_debate_state.get("judge_decision"),
        },
        "risk_debate_state": {
            "aggressive_history": risk_debate_state.get("aggressive_history"),
            "conservative_history": risk_debate_state.get("conservative_history"),
            "neutral_history": risk_debate_state.get("neutral_history"),
            "history": risk_debate_state.get("history"),
            "judge_decision": risk_debate_state.get("judge_decision"),
        },
    }


def _flush_captured_stdout(captured_stdout: io.StringIO) -> None:
    captured = captured_stdout.getvalue()
    if captured:
        print(captured, end="", file=sys.stderr)


def _parse_args(argv: Sequence[str]) -> tuple[str, str]:
    if not argv:
        _print_usage()
        raise ArgumentError("参数错误：缺少能力名。")

    command = argv[0]
    if command != "stock-analysis":
        _print_usage()
        raise ArgumentError(f"参数错误：未知能力 '{command}'。")

    if len(argv) < 2:
        _print_usage()
        raise ArgumentError("参数错误：缺少必填股票代码 ticker。")
    if len(argv) > 2:
        _print_usage()
        raise ArgumentError("参数错误：stock-analysis 只接受一个 ticker 参数。")

    return command, validate_ticker(argv[1])


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)
    args = list(sys.argv[1:] if argv is None else argv)

    try:
        command, ticker = _parse_args(args)
        if command == "stock-analysis":
            markdown = run_stock_analysis(ticker)
            sys.stdout.write(markdown)
            sys.stdout.write("\n")
        return EXIT_OK
    except SkillCliError as exc:
        print(str(exc), file=sys.stderr)
        if not isinstance(exc, ArgumentError) and exc.__cause__ is not None:
            traceback.print_exception(
                type(exc.__cause__),
                exc.__cause__,
                exc.__cause__.__traceback__,
                file=sys.stderr,
            )
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
