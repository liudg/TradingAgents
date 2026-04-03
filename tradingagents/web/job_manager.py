import json
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
    HistoricalReportAgentGroup,
    HistoricalReportDetail,
    HistoricalReportItem,
    HistoricalReportSummary,
    JobStatus,
)


ANALYST_REPORT_SECTIONS = [
    ("market", "市场技术分析师", "market_report", "市场技术分析报告"),
    ("social", "社交情绪分析师", "sentiment_report", "社交情绪分析报告"),
    ("news", "新闻分析师", "news_report", "新闻分析报告"),
    ("fundamentals", "基本面分析师", "fundamentals_report", "基本面分析报告"),
]

RESEARCH_REPORT_SECTIONS = [
    ("bull", "Bull Researcher", "bull_history", "多方研究报告"),
    ("bear", "Bear Researcher", "bear_history", "空方研究报告"),
    ("manager", "Research Manager", "judge_decision", "研究经理决策报告"),
]

RISK_REPORT_SECTIONS = [
    ("aggressive", "Aggressive Analyst", "aggressive_history", "激进风险分析报告"),
    (
        "conservative",
        "Conservative Analyst",
        "conservative_history",
        "保守风险分析报告",
    ),
    ("neutral", "Neutral Analyst", "neutral_history", "中性风险分析报告"),
    ("manager", "Portfolio Manager", "judge_decision", "组合经理最终决策"),
]


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
        self._restore_persisted_jobs()

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

    def list_historical_reports(self) -> list[HistoricalReportSummary]:
        with self._lock:
            snapshots = [
                dict(job_data)
                for job_data in self._jobs.values()
                if job_data.get("status") == JobStatus.COMPLETED
                and job_data.get("report_path")
            ]

        reports = [self._build_report_summary(snapshot) for snapshot in snapshots]
        return sorted(reports, key=lambda item: item.generated_at, reverse=True)

    def get_historical_report(self, job_id: str) -> HistoricalReportDetail:
        with self._lock:
            job_data = self._jobs.get(job_id)
            if job_data is None:
                raise KeyError(job_id)
            snapshot = dict(job_data)

        if (
            snapshot.get("status") != JobStatus.COMPLETED
            or not snapshot.get("report_path")
        ):
            raise ValueError(
                f"Report for job '{job_id}' is not ready. Current status: {snapshot.get('status')}"
            )

        summary = self._build_report_summary(snapshot)
        return HistoricalReportDetail(
            **summary.model_dump(),
            agent_reports=self._build_agent_reports(snapshot.get("final_state") or {}),
        )

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
            self._persist_completed_job_snapshot(job_id)
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

    def _restore_persisted_jobs(self) -> None:
        self.reports_root.mkdir(parents=True, exist_ok=True)
        for snapshot_path in self.reports_root.glob("*/job_snapshot.json"):
            try:
                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                request = AnalysisJobRequest.model_validate(payload["request"])
                job_data = {
                    "job_id": payload["job_id"],
                    "status": JobStatus(payload["status"]),
                    "progress": payload.get("progress", 100),
                    "request": request,
                    "final_state": payload.get("final_state"),
                    "decision": payload.get("decision"),
                    "error_message": payload.get("error_message"),
                    "report_path": payload.get("report_path"),
                    "created_at": datetime.fromisoformat(payload["created_at"]),
                    "started_at": self._parse_optional_datetime(
                        payload.get("started_at")
                    ),
                    "finished_at": self._parse_optional_datetime(
                        payload.get("finished_at")
                    ),
                }
            except Exception:
                continue

            self._jobs[job_data["job_id"]] = job_data

    def _persist_completed_job_snapshot(self, job_id: str) -> None:
        with self._lock:
            job_data = self._jobs.get(job_id)
            if not job_data:
                return
            snapshot = dict(job_data)

        report_path = snapshot.get("report_path")
        if not report_path:
            return

        payload = {
            "job_id": snapshot["job_id"],
            "status": snapshot["status"].value,
            "progress": snapshot["progress"],
            "request": snapshot["request"].model_dump(mode="json"),
            "final_state": snapshot.get("final_state"),
            "decision": snapshot.get("decision"),
            "error_message": snapshot.get("error_message"),
            "report_path": snapshot.get("report_path"),
            "created_at": snapshot["created_at"].isoformat(),
            "started_at": self._format_optional_datetime(snapshot.get("started_at")),
            "finished_at": self._format_optional_datetime(snapshot.get("finished_at")),
        }
        snapshot_path = Path(report_path).parent / "job_snapshot.json"
        snapshot_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _format_optional_datetime(value: Optional[datetime]) -> Optional[str]:
        return value.isoformat() if value else None

    @staticmethod
    def _parse_optional_datetime(value: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(value) if value else None

    @staticmethod
    def _build_report_summary(snapshot: Dict[str, Any]) -> HistoricalReportSummary:
        request = snapshot["request"]
        return HistoricalReportSummary(
            job_id=snapshot["job_id"],
            ticker=request.ticker,
            trade_date=request.trade_date,
            generated_at=snapshot.get("finished_at")
            or snapshot.get("started_at")
            or snapshot["created_at"],
            selected_analysts=[item.value for item in request.selected_analysts],
            llm_provider=request.llm_provider,
            deep_think_llm=request.deep_think_llm,
            quick_think_llm=request.quick_think_llm,
            max_debate_rounds=request.max_debate_rounds,
            max_risk_discuss_rounds=request.max_risk_discuss_rounds,
            max_recur_limit=request.max_recur_limit,
            report_path=snapshot.get("report_path"),
        )

    @staticmethod
    def _build_agent_reports(final_state: Dict[str, Any]) -> list[HistoricalReportAgentGroup]:
        groups: list[HistoricalReportAgentGroup] = []

        for agent_key, agent_name, field_name, title in ANALYST_REPORT_SECTIONS:
            content = final_state.get(field_name)
            if content and str(content).strip():
                groups.append(
                    HistoricalReportAgentGroup(
                        agent_key=agent_key,
                        agent_name=agent_name,
                        reports=[
                            HistoricalReportItem(
                                report_key=field_name,
                                title=title,
                                content=str(content),
                            )
                        ],
                    )
                )

        research_reports = []
        investment_debate_state = final_state.get("investment_debate_state") or {}
        for report_key, _, field_name, title in RESEARCH_REPORT_SECTIONS:
            content = investment_debate_state.get(field_name)
            if content and str(content).strip():
                research_reports.append(
                    HistoricalReportItem(
                        report_key=f"research_{report_key}",
                        title=title,
                        content=str(content),
                    )
                )
        if final_state.get("investment_plan"):
            research_reports.append(
                HistoricalReportItem(
                    report_key="investment_plan",
                    title="研究经理投资计划",
                    content=str(final_state["investment_plan"]),
                )
            )
        if research_reports:
            groups.append(
                HistoricalReportAgentGroup(
                    agent_key="research_team",
                    agent_name="研究团队",
                    reports=research_reports,
                )
            )

        if final_state.get("trader_investment_plan"):
            groups.append(
                HistoricalReportAgentGroup(
                    agent_key="trader",
                    agent_name="交易员",
                    reports=[
                        HistoricalReportItem(
                            report_key="trader_investment_plan",
                            title="交易员执行方案",
                            content=str(final_state["trader_investment_plan"]),
                        )
                    ],
                )
            )

        risk_reports = []
        risk_debate_state = final_state.get("risk_debate_state") or {}
        for report_key, _, field_name, title in RISK_REPORT_SECTIONS:
            content = risk_debate_state.get(field_name)
            if content and str(content).strip():
                risk_reports.append(
                    HistoricalReportItem(
                        report_key=f"risk_{report_key}",
                        title=title,
                        content=str(content),
                    )
                )
        if final_state.get("final_trade_decision"):
            risk_reports.append(
                HistoricalReportItem(
                    report_key="final_trade_decision",
                    title="最终交易决策",
                    content=str(final_state["final_trade_decision"]),
                )
            )
        if risk_reports:
            groups.append(
                HistoricalReportAgentGroup(
                    agent_key="risk_team",
                    agent_name="风控团队",
                    reports=risk_reports,
                )
            )

        return groups
