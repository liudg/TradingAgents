import json
import re
import traceback
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

import pandas as pd
import yfinance as yf

from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import save_report_to_disk
from tradingagents.web.job_manager import AnalysisJobManager
from tradingagents.web.schemas import (
    AnalysisJobLogEntry,
    BacktestJobRequest,
    BacktestJobResponse,
    BacktestMemoryEntry,
    BacktestSampleEvaluation,
    BacktestSummary,
    HistoricalBacktestDetail,
    HistoricalBacktestSummary,
    JobStatus,
)


class BacktestJobManager:
    def __init__(
        self,
        backtests_root: Optional[Path] = None,
        max_workers: int = 2,
    ) -> None:
        self.backtests_root = backtests_root or Path(DEFAULT_CONFIG["results_dir"]) / "backtests"
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._restore_persisted_jobs()

    def create_job(self, request: BacktestJobRequest) -> BacktestJobResponse:
        job_id = uuid4().hex
        normalized_request = request.model_copy(
            update={
                "selected_analysts": AnalysisJobManager._normalize_selected_analysts(
                    request.selected_analysts
                )
            }
        )
        results_dir = self._get_results_dir(normalized_request, job_id)
        job_data = {
            "job_id": job_id,
            "status": JobStatus.PENDING,
            "progress": 0,
            "stage": "queued",
            "memory_commit_status": "not_requested",
            "request": normalized_request,
            "summary": None,
            "samples": [],
            "memory_entries": [],
            "error_message": None,
            "log_path": str(results_dir / "backtest.log"),
            "results_dir": str(results_dir),
            "created_at": datetime.now(),
            "started_at": None,
            "finished_at": None,
        }
        with self._lock:
            self._jobs[job_id] = job_data

        self._executor.submit(self._run_job, job_id)
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> BacktestJobResponse:
        return BacktestJobResponse(**self._get_job_snapshot(job_id))

    def _get_job_snapshot(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job_data = self._jobs.get(job_id)
            if job_data is None:
                raise KeyError(job_id)
            return dict(job_data)

    def list_job_logs(self, job_id: str) -> list[AnalysisJobLogEntry]:
        snapshot = self._get_job_snapshot(job_id)
        log_path = Path(snapshot.get("log_path") or Path(snapshot["results_dir"]) / "backtest.log")
        if not log_path.exists():
            return []

        entries: list[AnalysisJobLogEntry] = []
        for line_no, raw_line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
            entries.append(AnalysisJobManager._parse_job_log_line(line_no, raw_line))
        return entries

    def list_historical_backtests(self) -> list[HistoricalBacktestSummary]:
        with self._lock:
            snapshots = [
                dict(job_data)
                for job_data in self._jobs.values()
                if job_data.get("status") == JobStatus.COMPLETED and job_data.get("summary")
            ]
        reports = [self._build_backtest_summary(snapshot) for snapshot in snapshots]
        return sorted(reports, key=lambda item: item.generated_at, reverse=True)

    def get_historical_backtest(self, job_id: str) -> HistoricalBacktestDetail:
        with self._lock:
            job_data = self._jobs.get(job_id)
            if job_data is None:
                raise KeyError(job_id)
            snapshot = dict(job_data)

        if snapshot.get("status") != JobStatus.COMPLETED or not snapshot.get("summary"):
            raise ValueError(
                f"Backtest for job '{job_id}' is not ready. Current status: {snapshot.get('status')}"
            )

        summary = self._build_backtest_summary(snapshot)
        return HistoricalBacktestDetail(
            **summary.model_dump(),
            summary=snapshot.get("summary"),
            samples=snapshot.get("samples") or [],
            memory_entries=snapshot.get("memory_entries") or [],
        )

    def _run_job(self, job_id: str) -> None:
        snapshot = self._get_job_snapshot(job_id)
        request: BacktestJobRequest = snapshot["request"]
        results_dir = Path(snapshot["results_dir"])
        runs_dir = results_dir / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        log_path = results_dir / "backtest.log"

        self._update_job(
            job_id,
            status=JobStatus.RUNNING,
            progress=5,
            stage="historical_run",
            started_at=datetime.now(),
        )
        AnalysisJobManager._append_job_log(
            log_path,
            "System",
            (
                f"Backtest job {job_id} started: ticker={request.ticker}, "
                f"start_date={request.start_date.isoformat()}, "
                f"end_date={request.end_date.isoformat()}, "
                f"holding_period={request.holding_period}, "
                f"reflection_enabled={request.reflection_enabled}, "
                f"writeback_enabled={request.writeback_enabled}"
            ),
        )

        try:
            price_frame = self._fetch_price_history(
                request.ticker,
                request.start_date - timedelta(days=10),
                request.end_date + timedelta(days=max(20, request.holding_period * 3)),
            )
            trade_dates = self._select_trade_dates(
                price_frame,
                request.start_date,
                request.end_date,
            )
            if not trade_dates:
                raise RuntimeError("No trading sessions found in the selected backtest range")

            config = self._build_config(request)
            graph = TradingAgentsGraph(
                selected_analysts=[item.value for item in request.selected_analysts],
                debug=False,
                config=config,
            )

            sample_contexts: list[dict[str, Any]] = []
            total_runs = len(trade_dates)
            for index, trade_date in enumerate(trade_dates, start=1):
                AnalysisJobManager._append_job_log(
                    log_path,
                    "System",
                    f"Running historical analysis for {trade_date.isoformat()} ({index}/{total_runs})",
                )
                final_state, decision = graph.propagate(
                    request.ticker,
                    trade_date.isoformat(),
                )
                safe_final_state = AnalysisJobManager._serialize_final_state(final_state)
                sample_dir = runs_dir / trade_date.isoformat()
                report_path = save_report_to_disk(
                    safe_final_state,
                    request.ticker,
                    sample_dir / "reports",
                )
                full_state_path = self._resolve_eval_state_path(
                    request.ticker,
                    trade_date,
                )
                sample = BacktestSampleEvaluation(
                    trade_date=trade_date,
                    signal=self._normalize_signal(decision),
                    raw_decision=str(safe_final_state.get("final_trade_decision") or decision or ""),
                    full_state_path=str(full_state_path) if full_state_path else None,
                    report_path=str(report_path),
                    holding_period=request.holding_period,
                    outcome_label="pending",
                    evaluation_status="pending",
                )
                sample_contexts.append({"sample": sample, "state": safe_final_state})
                progress = 5 + int(index / total_runs * 50)
                self._update_job(
                    job_id,
                    progress=min(progress, 55),
                    samples=[item["sample"] for item in sample_contexts],
                )

            self._update_job(job_id, stage="evaluate", progress=60)
            AnalysisJobManager._append_job_log(log_path, "System", "Evaluating historical decisions")
            for sample_context in sample_contexts:
                sample_context["sample"] = self._evaluate_sample(
                    sample_context["sample"],
                    price_frame,
                )
            self._update_job(
                job_id,
                progress=75,
                samples=[item["sample"] for item in sample_contexts],
            )

            memory_entries: list[BacktestMemoryEntry] = []
            memory_entry_dates: set[date] = set()
            if request.reflection_enabled:
                self._update_job(job_id, stage="reflect", progress=80)
                AnalysisJobManager._append_job_log(log_path, "System", "Generating structured reflections")
                for sample_context in sample_contexts:
                    sample = sample_context["sample"]
                    if not self._should_reflect(sample):
                        continue
                    reflection_payload = self._generate_structured_reflection(
                        graph,
                        sample,
                        sample_context["state"],
                    )
                    sample.reflection_payload = reflection_payload
                    sample.reflection_text = reflection_payload.get("reusable_rule") or reflection_payload.get("what_should_change")

                    if request.writeback_enabled and self._should_write_memory(sample):
                        memory_payload = self._write_memory_entry(
                            request,
                            sample,
                            reflection_payload,
                            sample_context["state"],
                        )
                        if memory_payload is not None:
                            memory_entries.append(memory_payload)
                            memory_entry_dates.add(sample.trade_date)
                            AnalysisJobManager._append_job_log(
                                log_path,
                                "System",
                                f"Queued memory candidate for {sample.trade_date.isoformat()}",
                            )

                self._update_job(
                    job_id,
                    progress=92,
                    samples=[item["sample"] for item in sample_contexts],
                    memory_entries=memory_entries,
                    memory_commit_status=(
                        "pending_commit" if request.writeback_enabled and memory_entries else "not_requested"
                    ),
                )

            if request.writeback_enabled:
                self._update_job(
                    job_id,
                    stage="commit_memory",
                    progress=96,
                    memory_commit_status="pending_commit" if memory_entries else "committed",
                )
                if memory_entries:
                    AnalysisJobManager._append_job_log(
                        log_path,
                        "System",
                        f"Committing {len(memory_entries)} memory entries",
                    )
                    self._commit_memory_entries(request, memory_entries)
                    for sample_context in sample_contexts:
                        if sample_context["sample"].trade_date in memory_entry_dates:
                            sample_context["sample"].memory_written = True
                self._update_job(
                    job_id,
                    samples=[item["sample"] for item in sample_contexts],
                    memory_entries=memory_entries,
                    memory_commit_status="committed",
                )

            summary = self._summarize_backtest(
                request.ticker,
                [item["sample"] for item in sample_contexts],
                memory_entries,
            )
            self._persist_backtest_artifacts(results_dir, summary, sample_contexts, memory_entries)
            self._update_job(
                job_id,
                status=JobStatus.COMPLETED,
                progress=100,
                stage="completed",
                summary=summary,
                samples=[item["sample"] for item in sample_contexts],
                memory_entries=memory_entries,
                memory_commit_status="committed" if request.writeback_enabled else "not_requested",
                finished_at=datetime.now(),
            )
            self._persist_job_snapshot(job_id)
        except Exception as exc:
            memory_commit_status = "skipped_due_to_failure" if request.writeback_enabled else "not_requested"
            self._update_job(
                job_id,
                memory_commit_status=memory_commit_status,
                samples=[item["sample"] for item in locals().get("sample_contexts", [])],
                memory_entries=locals().get("memory_entries", []),
            )
            if request.writeback_enabled:
                AnalysisJobManager._append_job_log(
                    log_path,
                    "System",
                    "Memory commit skipped because the backtest job failed",
                )
            AnalysisJobManager._append_job_log(
                log_path,
                "Error",
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            )
            self._update_job(
                job_id,
                status=JobStatus.FAILED,
                progress=100,
                stage="failed",
                error_message=str(exc),
                finished_at=datetime.now(),
            )
            self._persist_job_snapshot(job_id)

    def _update_job(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            if job_id not in self._jobs:
                return
            self._jobs[job_id].update(changes)

    @staticmethod
    def _build_config(request: BacktestJobRequest) -> Dict[str, Any]:
        config = deepcopy(DEFAULT_CONFIG)
        config["llm_provider"] = request.llm_provider
        config["deep_think_llm"] = request.deep_think_llm
        config["quick_think_llm"] = request.quick_think_llm
        config["backend_url"] = request.backend_url
        config["google_thinking_level"] = request.google_thinking_level
        config["openai_reasoning_effort"] = request.openai_reasoning_effort
        config["anthropic_effort"] = request.anthropic_effort
        config["output_language"] = request.output_language
        config["max_debate_rounds"] = request.max_debate_rounds
        config["max_risk_discuss_rounds"] = request.max_risk_discuss_rounds
        return config

    @staticmethod
    def _fetch_price_history(ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
        frame = yf.download(
            ticker,
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            progress=False,
            auto_adjust=True,
            multi_level_index=False,
        )
        if frame.empty:
            raise RuntimeError(f"No price data found for {ticker}")
        frame = frame.reset_index()
        frame["Date"] = pd.to_datetime(frame["Date"]).dt.tz_localize(None)
        frame = frame.dropna(subset=["Date", "Open", "Close"])
        frame["DateOnly"] = frame["Date"].dt.date
        return frame

    @staticmethod
    def _select_trade_dates(price_frame: pd.DataFrame, start_date: date, end_date: date) -> list[date]:
        rows = price_frame[
            (price_frame["DateOnly"] >= start_date)
            & (price_frame["DateOnly"] <= end_date)
        ]
        return list(rows["DateOnly"])

    @staticmethod
    def _resolve_eval_state_path(ticker: str, trade_date: date) -> Optional[Path]:
        path = Path("eval_results") / ticker / "TradingAgentsStrategy_logs" / f"full_states_log_{trade_date.isoformat()}.json"
        return path if path.exists() else None

    @staticmethod
    def _normalize_signal(decision: str) -> str:
        normalized = str(decision or "").upper()
        if "BUY" in normalized:
            return "BUY"
        if "SELL" in normalized:
            return "SELL"
        if "HOLD" in normalized:
            return "HOLD"
        return normalized or "UNKNOWN"

    def _evaluate_sample(
        self,
        sample: BacktestSampleEvaluation,
        price_frame: pd.DataFrame,
    ) -> BacktestSampleEvaluation:
        rows = price_frame.reset_index(drop=True)
        trade_row_matches = rows.index[rows["DateOnly"] == sample.trade_date].tolist()
        if not trade_row_matches:
            sample.evaluation_status = "skipped"
            sample.outcome_label = "no_trade_session"
            sample.notes = "The requested analysis date is not a trading session."
            return sample

        trade_row_index = trade_row_matches[0]
        if trade_row_index + 1 >= len(rows):
            sample.evaluation_status = "skipped"
            sample.outcome_label = "insufficient_future_data"
            sample.notes = "No future session available for entry."
            return sample

        entry_index = trade_row_index + 1
        exit_index = min(entry_index + sample.holding_period - 1, len(rows) - 1)
        entry_row = rows.iloc[entry_index]
        exit_row = rows.iloc[exit_index]
        trade_row = rows.iloc[trade_row_index]

        sample.entry_date = entry_row["DateOnly"]
        sample.exit_date = exit_row["DateOnly"]
        sample.entry_price = float(entry_row["Open"])
        sample.exit_price = float(exit_row["Close"])
        sample.benchmark_return_pct = round(
            ((float(exit_row["Close"]) / float(trade_row["Close"])) - 1) * 100,
            4,
        )

        signal = sample.signal.upper()
        if signal == "SELL":
            sample.evaluation_status = "skipped"
            sample.outcome_label = "sell_not_scored"
            sample.notes = "SELL signals are captured but not scored in the MVP backtest."
            return sample

        if signal == "HOLD":
            sample.evaluation_status = "evaluated"
            sample.return_pct = 0.0
            sample.excess_return_pct = round(
                0.0 - (sample.benchmark_return_pct or 0.0),
                4,
            )
            sample.max_drawdown_pct = 0.0
            sample.outcome_label = self._label_hold_outcome(sample.benchmark_return_pct or 0.0)
            return sample

        if not sample.entry_price:
            sample.evaluation_status = "skipped"
            sample.outcome_label = "invalid_entry"
            sample.notes = "Entry price is missing."
            return sample

        window = rows.iloc[entry_index : exit_index + 1]
        min_low = float(window["Low"].min()) if "Low" in window.columns else float(window["Close"].min())
        sample.return_pct = round(((sample.exit_price / sample.entry_price) - 1) * 100, 4)
        sample.excess_return_pct = round(
            (sample.return_pct or 0.0) - (sample.benchmark_return_pct or 0.0),
            4,
        )
        sample.max_drawdown_pct = round(((min_low / sample.entry_price) - 1) * 100, 4)
        sample.evaluation_status = "evaluated"
        sample.outcome_label = "correct" if (sample.return_pct or 0.0) > 0 else "incorrect"
        return sample

    @staticmethod
    def _label_hold_outcome(benchmark_return_pct: float) -> str:
        if benchmark_return_pct >= 2.0:
            return "missed_opportunity"
        if benchmark_return_pct <= -2.0:
            return "avoided_loss"
        return "neutral"

    @staticmethod
    def _should_reflect(sample: BacktestSampleEvaluation) -> bool:
        if sample.evaluation_status != "evaluated":
            return False
        if sample.outcome_label in {"incorrect", "missed_opportunity"}:
            return True
        return bool(sample.excess_return_pct is not None and sample.excess_return_pct >= 3.0)

    @staticmethod
    def _should_write_memory(sample: BacktestSampleEvaluation) -> bool:
        if sample.evaluation_status != "evaluated":
            return False
        if sample.outcome_label in {"incorrect", "missed_opportunity"}:
            return True
        return bool(sample.excess_return_pct is not None and sample.excess_return_pct >= 4.0)

    def _generate_structured_reflection(
        self,
        graph: TradingAgentsGraph,
        sample: BacktestSampleEvaluation,
        final_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        prompt = (
            "You are reviewing a historical trading decision. "
            "Return strict JSON with keys: decision_quality, key_success_factors, "
            "key_failure_factors, what_should_change, reusable_rule, memory_query, confidence. "
            "Do not wrap the JSON in markdown.\n\n"
            f"Trade date: {sample.trade_date.isoformat()}\n"
            f"Signal: {sample.signal}\n"
            f"Outcome label: {sample.outcome_label}\n"
            f"Return pct: {sample.return_pct}\n"
            f"Benchmark return pct: {sample.benchmark_return_pct}\n"
            f"Excess return pct: {sample.excess_return_pct}\n"
            f"Max drawdown pct: {sample.max_drawdown_pct}\n"
            "Current state snapshot:\n"
            f"{json.dumps(final_state, ensure_ascii=False)}"
        )
        fallback = self._build_fallback_reflection(sample)
        try:
            raw_response = graph.quick_thinking_llm.invoke(prompt).content
            if not isinstance(raw_response, str):
                return fallback
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.DOTALL)
            payload = json.loads(cleaned)
            if not isinstance(payload, dict):
                return fallback
            return {
                "decision_quality": str(payload.get("decision_quality") or fallback["decision_quality"]),
                "key_success_factors": str(payload.get("key_success_factors") or fallback["key_success_factors"]),
                "key_failure_factors": str(payload.get("key_failure_factors") or fallback["key_failure_factors"]),
                "what_should_change": str(payload.get("what_should_change") or fallback["what_should_change"]),
                "reusable_rule": str(payload.get("reusable_rule") or fallback["reusable_rule"]),
                "memory_query": str(payload.get("memory_query") or fallback["memory_query"]),
                "confidence": str(payload.get("confidence") or fallback["confidence"]),
            }
        except Exception:
            return fallback

    @staticmethod
    def _build_fallback_reflection(sample: BacktestSampleEvaluation) -> Dict[str, Any]:
        if sample.outcome_label in {"incorrect", "missed_opportunity"}:
            change = "Tighten entry quality and require stronger agreement between market, news, sentiment, and fundamentals before issuing BUY."
            rule = "When evidence is mixed or forward returns turn negative after a BUY call, prefer HOLD until catalysts and trend align."
            quality = "needs_improvement"
            failure_factors = "The final decision overweighted weak or conflicting evidence relative to realized price behavior."
            success_factors = "The backtest sample still captured a full multi-agent state that can be reused for pattern matching."
        else:
            change = "Keep the same posture when multiple analysts align and subsequent price action confirms the thesis."
            rule = "Reinforce setups where analyst alignment is followed by positive forward returns and limited drawdown."
            quality = "strong"
            failure_factors = "No material failure factor identified in this sample."
            success_factors = "The decision aligned with subsequent price action and maintained acceptable drawdown."
        return {
            "decision_quality": quality,
            "key_success_factors": success_factors,
            "key_failure_factors": failure_factors,
            "what_should_change": change,
            "reusable_rule": rule,
            "memory_query": f"{sample.signal} {sample.outcome_label} return {sample.return_pct}",
            "confidence": "medium",
        }

    @staticmethod
    def _commit_memory_entries(
        request: BacktestJobRequest,
        memory_entries: list[BacktestMemoryEntry],
    ) -> None:
        if not memory_entries:
            return

        memory = FinancialSituationMemory(
            memory_entries[0].memory_type,
            BacktestJobManager._build_config(request),
        )
        memory.add_situations(
            [
                (entry.memory_query, entry.recommendation)
                for entry in memory_entries
            ]
        )

    def _write_memory_entry(
        self,
        request: BacktestJobRequest,
        sample: BacktestSampleEvaluation,
        reflection_payload: Dict[str, Any],
        final_state: Dict[str, Any],
    ) -> Optional[BacktestMemoryEntry]:
        recommendation = "\n".join(
            [
                f"Rule: {reflection_payload.get('reusable_rule', '')}",
                f"Adjustment: {reflection_payload.get('what_should_change', '')}",
                f"Outcome: {sample.outcome_label} ({sample.return_pct}%)",
            ]
        ).strip()
        memory_query = str(reflection_payload.get("memory_query") or "").strip()
        if not recommendation or not memory_query:
            return None

        situation = "\n\n".join(
            str(final_state.get(key) or "")
            for key in [
                "market_report",
                "sentiment_report",
                "news_report",
                "fundamentals_report",
            ]
        ).strip()
        return BacktestMemoryEntry(
            memory_type="trader_memory",
            trade_date=sample.trade_date,
            signal=sample.signal,
            return_pct=sample.return_pct,
            outcome_label=sample.outcome_label,
            memory_query=situation or memory_query,
            recommendation=recommendation,
        )

    @staticmethod
    def _summarize_backtest(
        ticker: str,
        samples: list[BacktestSampleEvaluation],
        memory_entries: list[BacktestMemoryEntry],
    ) -> BacktestSummary:
        evaluated = [
            sample for sample in samples
            if sample.evaluation_status == "evaluated" and sample.return_pct is not None
        ]
        buy_samples = [sample for sample in evaluated if sample.signal == "BUY"]
        hold_samples = [sample for sample in evaluated if sample.signal == "HOLD"]
        sell_samples = [sample for sample in samples if sample.signal == "SELL"]
        avg_return = (
            round(sum(sample.return_pct or 0.0 for sample in evaluated) / len(evaluated), 4)
            if evaluated
            else None
        )
        avg_benchmark = (
            round(sum(sample.benchmark_return_pct or 0.0 for sample in evaluated) / len(evaluated), 4)
            if evaluated
            else None
        )
        avg_excess = (
            round(sum(sample.excess_return_pct or 0.0 for sample in evaluated) / len(evaluated), 4)
            if evaluated
            else None
        )
        cumulative = (
            round(((float(pd.Series([(sample.return_pct or 0.0) / 100 for sample in evaluated]).add(1).prod()) - 1) * 100), 4)
            if evaluated
            else None
        )
        max_drawdown = (
            round(min(sample.max_drawdown_pct or 0.0 for sample in buy_samples), 4)
            if buy_samples
            else None
        )
        win_rate = (
            round((sum(1 for sample in buy_samples if (sample.return_pct or 0.0) > 0) / len(buy_samples)) * 100, 2)
            if buy_samples
            else None
        )
        reflection_count = sum(1 for sample in samples if sample.reflection_payload)
        return BacktestSummary(
            ticker=ticker,
            sample_count=len(samples),
            evaluated_count=len(evaluated),
            buy_count=len(buy_samples),
            hold_count=len(hold_samples),
            sell_count=len(sell_samples),
            win_rate=win_rate,
            avg_return_pct=avg_return,
            benchmark_avg_return_pct=avg_benchmark,
            excess_return_pct=avg_excess,
            cumulative_return_pct=cumulative,
            max_drawdown_pct=max_drawdown,
            reflection_count=reflection_count,
            memory_write_count=len(memory_entries),
        )

    @staticmethod
    def _persist_backtest_artifacts(
        results_dir: Path,
        summary: BacktestSummary,
        sample_contexts: list[dict[str, Any]],
        memory_entries: list[BacktestMemoryEntry],
    ) -> None:
        payload = {
            "summary": summary.model_dump(mode="json"),
            "samples": [item["sample"].model_dump(mode="json") for item in sample_contexts],
            "memory_entries": [entry.model_dump(mode="json") for entry in memory_entries],
        }
        (results_dir / "backtest_results.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _restore_persisted_jobs(self) -> None:
        self.backtests_root.mkdir(parents=True, exist_ok=True)
        for snapshot_path in self.backtests_root.rglob("backtest_snapshot.json"):
            try:
                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                request = BacktestJobRequest.model_validate(payload["request"])
                job_data = {
                    "job_id": payload["job_id"],
                    "status": JobStatus(payload["status"]),
                    "progress": payload.get("progress", 100),
                    "stage": payload.get("stage", "completed"),
                    "memory_commit_status": payload.get("memory_commit_status", "not_requested"),
                    "request": request,
                    "summary": BacktestSummary.model_validate(payload["summary"]) if payload.get("summary") else None,
                    "samples": [BacktestSampleEvaluation.model_validate(item) for item in payload.get("samples", [])],
                    "memory_entries": [BacktestMemoryEntry.model_validate(item) for item in payload.get("memory_entries", [])],
                    "error_message": payload.get("error_message"),
                    "log_path": payload.get("log_path") or str(snapshot_path.parent / "backtest.log"),
                    "results_dir": payload.get("results_dir") or str(snapshot_path.parent),
                    "created_at": datetime.fromisoformat(payload["created_at"]),
                    "started_at": AnalysisJobManager._parse_optional_datetime(payload.get("started_at")),
                    "finished_at": AnalysisJobManager._parse_optional_datetime(payload.get("finished_at")),
                }
            except Exception:
                continue
            self._jobs[job_data["job_id"]] = job_data

    def _persist_job_snapshot(self, job_id: str) -> None:
        with self._lock:
            job_data = self._jobs.get(job_id)
            if job_data is None:
                return
            snapshot = dict(job_data)

        snapshot_dir = Path(snapshot["results_dir"])
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "job_id": snapshot["job_id"],
            "status": snapshot["status"].value,
            "progress": snapshot["progress"],
            "stage": snapshot["stage"],
            "memory_commit_status": snapshot.get("memory_commit_status", "not_requested"),
            "request": snapshot["request"].model_dump(mode="json"),
            "summary": snapshot["summary"].model_dump(mode="json") if snapshot.get("summary") else None,
            "samples": [sample.model_dump(mode="json") for sample in snapshot.get("samples", [])],
            "memory_entries": [entry.model_dump(mode="json") for entry in snapshot.get("memory_entries", [])],
            "error_message": snapshot.get("error_message"),
            "log_path": snapshot.get("log_path"),
            "results_dir": snapshot.get("results_dir"),
            "created_at": snapshot["created_at"].isoformat(),
            "started_at": AnalysisJobManager._format_optional_datetime(snapshot.get("started_at")),
            "finished_at": AnalysisJobManager._format_optional_datetime(snapshot.get("finished_at")),
        }
        (snapshot_dir / "backtest_snapshot.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _get_results_dir(self, request: BacktestJobRequest, job_id: str) -> Path:
        range_key = f"{request.start_date.isoformat()}_{request.end_date.isoformat()}"
        return self.backtests_root / request.ticker / range_key / job_id

    @staticmethod
    def _build_backtest_summary(snapshot: Dict[str, Any]) -> HistoricalBacktestSummary:
        request = snapshot["request"]
        summary: BacktestSummary = snapshot["summary"]
        return HistoricalBacktestSummary(
            job_id=snapshot["job_id"],
            ticker=request.ticker,
            start_date=request.start_date,
            end_date=request.end_date,
            generated_at=snapshot.get("finished_at") or snapshot.get("started_at") or snapshot["created_at"],
            memory_commit_status=snapshot.get("memory_commit_status", "not_requested"),
            holding_period=request.holding_period,
            selected_analysts=[item.value for item in request.selected_analysts],
            llm_provider=request.llm_provider,
            deep_think_llm=request.deep_think_llm,
            quick_think_llm=request.quick_think_llm,
            output_language=request.output_language,
            sample_count=summary.sample_count,
            evaluated_count=summary.evaluated_count,
            win_rate=summary.win_rate,
            avg_return_pct=summary.avg_return_pct,
            excess_return_pct=summary.excess_return_pct,
            reflection_count=summary.reflection_count,
            memory_write_count=summary.memory_write_count,
        )
