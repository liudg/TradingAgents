from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import save_report_to_disk
from tradingagents.web.schemas import (
    AnalysisJobRequest,
    AnalysisJobResponse,
    JobStatus,
)


class AnalysisJobManager:
    def __init__(
        self,
        reports_root: Optional[Path] = None,
        max_workers: int = 4,
    ) -> None:
        self.reports_root = reports_root or Path.cwd() / "reports" / "web"
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def create_job(self, request: AnalysisJobRequest) -> AnalysisJobResponse:
        job_id = uuid4().hex
        job_data = {
            "job_id": job_id,
            "status": JobStatus.PENDING,
            "progress": 0,
            "request": request,
            "final_state": None,
            "decision": None,
            "error_message": None,
            "report_path": None,
            "created_at": datetime.now(),
            "started_at": None,
            "finished_at": None,
        }

        with self._lock:
            self._jobs[job_id] = job_data

        self._executor.submit(self._run_job, job_id)
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> AnalysisJobResponse:
        with self._lock:
            job_data = self._jobs.get(job_id)
            if job_data is None:
                raise KeyError(job_id)
            snapshot = dict(job_data)
        return AnalysisJobResponse(**snapshot)

    def get_report_path(self, job_id: str) -> Path:
        job = self.get_job(job_id)
        if job.status != JobStatus.COMPLETED or not job.report_path:
            raise ValueError(
                f"Report for job '{job_id}' is not ready. Current status: {job.status}"
            )
        return Path(job.report_path)

    def _run_job(self, job_id: str) -> None:
        self._update_job(
            job_id,
            status=JobStatus.RUNNING,
            progress=5,
            started_at=datetime.now(),
        )

        try:
            request = self.get_job(job_id).request
            config = self._build_config(request)
            graph = TradingAgentsGraph(
                selected_analysts=[item.value for item in request.selected_analysts],
                debug=False,
                config=config,
            )
            self._update_job(job_id, progress=30)

            final_state, decision = graph.propagate(
                request.ticker,
                request.trade_date.isoformat(),
            )
            safe_final_state = self._serialize_final_state(final_state)
            self._update_job(job_id, progress=90)

            report_dir = self.reports_root / job_id
            report_path = save_report_to_disk(
                safe_final_state,
                request.ticker,
                report_dir,
            )
            self._update_job(
                job_id,
                status=JobStatus.COMPLETED,
                progress=100,
                final_state=safe_final_state,
                decision=decision,
                report_path=str(report_path),
                finished_at=datetime.now(),
            )
        except Exception as exc:
            self._update_job(
                job_id,
                status=JobStatus.FAILED,
                progress=100,
                error_message=str(exc),
                finished_at=datetime.now(),
            )

    def _update_job(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(changes)

    @staticmethod
    def _build_config(request: AnalysisJobRequest) -> Dict[str, Any]:
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
        config["max_recur_limit"] = request.max_recur_limit
        return config

    @staticmethod
    def _serialize_final_state(final_state: Dict[str, Any]) -> Dict[str, Any]:
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
                "conservative_history": risk_debate_state.get(
                    "conservative_history"
                ),
                "neutral_history": risk_debate_state.get("neutral_history"),
                "history": risk_debate_state.get("history"),
                "judge_decision": risk_debate_state.get("judge_decision"),
            },
        }
