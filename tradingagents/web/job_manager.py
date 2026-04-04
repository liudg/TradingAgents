import json
import re
import traceback
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.reporting import save_report_to_disk
from tradingagents.web.schemas import (
    AnalysisJobLogEntry,
    AnalysisJobRequest,
    AnalysisJobResponse,
    HistoricalReportAgentGroup,
    HistoricalReportDetail,
    HistoricalReportItem,
    HistoricalReportSummary,
    JobStatus,
)


ANALYST_ORDER = ["market", "social", "news", "fundamentals"]
REPORT_PROGRESS_WEIGHTS = {
    "market_report": 12,
    "sentiment_report": 12,
    "news_report": 12,
    "fundamentals_report": 12,
    "investment_plan": 15,
    "trader_investment_plan": 15,
    "final_trade_decision": 17,
}
JOB_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"\[(?P<level>[^\]]+)\] "
    r"(?P<content>.*)$"
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
        self.reports_root = reports_root or Path(DEFAULT_CONFIG["results_dir"])
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._restore_persisted_jobs()

    def create_job(self, request: AnalysisJobRequest) -> AnalysisJobResponse:
        job_id = uuid4().hex
        normalized_request = request.model_copy(
            update={
                "selected_analysts": self._normalize_selected_analysts(
                    request.selected_analysts
                )
            }
        )
        results_dir = self._get_results_dir(normalized_request, job_id)
        job_data = {
            "job_id": job_id,
            "status": JobStatus.PENDING,
            "progress": 0,
            "request": normalized_request,
            "final_state": None,
            "decision": None,
            "error_message": None,
            "report_path": None,
            "log_path": str(results_dir / "message_tool.log"),
            "results_dir": str(results_dir),
            "created_at": datetime.now(),
            "started_at": None,
            "finished_at": None,
        }

        with self._lock:
            self._jobs[job_id] = job_data

        self._executor.submit(self._run_job, job_id)
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> AnalysisJobResponse:
        return AnalysisJobResponse(**self._get_job_snapshot(job_id))

    def _get_job_snapshot(self, job_id: str) -> Dict[str, Any]:
        with self._lock:
            job_data = self._jobs.get(job_id)
            if job_data is None:
                raise KeyError(job_id)
            return dict(job_data)

    def get_report_path(self, job_id: str) -> Path:
        job = self.get_job(job_id)
        if job.status != JobStatus.COMPLETED or not job.report_path:
            raise ValueError(
                f"Report for job '{job_id}' is not ready. Current status: {job.status}"
            )
        return Path(job.report_path)

    def list_job_logs(self, job_id: str) -> list[AnalysisJobLogEntry]:
        snapshot = self._get_job_snapshot(job_id)
        log_path = Path(
            snapshot.get("log_path")
            or Path(snapshot["results_dir"]) / "message_tool.log"
        )
        if not log_path.exists():
            return []

        entries: list[AnalysisJobLogEntry] = []
        for line_no, raw_line in enumerate(
            log_path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            entries.append(self._parse_job_log_line(line_no, raw_line))
        return entries

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
        snapshot = self._get_job_snapshot(job_id)
        request = snapshot["request"]
        results_dir = Path(snapshot["results_dir"])
        report_dir = results_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        log_path = results_dir / "message_tool.log"

        self._update_job(
            job_id,
            status=JobStatus.RUNNING,
            progress=5,
            log_path=str(log_path),
            started_at=datetime.now(),
        )
        self._append_job_log(
            log_path,
            "System",
            (
                f"Job {job_id} started: ticker={request.ticker}, "
                f"trade_date={request.trade_date.isoformat()}, "
                f"analysts={','.join(item.value for item in request.selected_analysts)}, "
                f"provider={request.llm_provider}, "
                f"deep_model={request.deep_think_llm}, "
                f"quick_model={request.quick_think_llm}, "
                f"backend_url={request.backend_url}, "
                f"output_language={request.output_language}"
            ),
        )

        try:
            config = self._build_config(request)
            message_logger = _StreamingMessageLogger(
                log_path=log_path,
                selected_analysts=[item.value for item in request.selected_analysts],
            )
            graph = TradingAgentsGraph(
                selected_analysts=[item.value for item in request.selected_analysts],
                debug=True,
                config=config,
            )
            self._update_job(job_id, progress=10)
            self._append_job_log(log_path, "System", "Trading graph initialized")

            init_agent_state = graph.propagator.create_initial_state(
                request.ticker,
                request.trade_date.isoformat(),
            )
            args = graph.propagator.get_graph_args()
            trace = []
            for chunk in graph.graph.stream(init_agent_state, **args):
                trace.append(chunk)
                progress = message_logger.process_chunk(chunk)
                self._update_job(job_id, progress=max(10, min(progress, 95)))

            if not trace:
                raise RuntimeError("Trading graph returned no streamed chunks")

            final_state = trace[-1]
            graph.curr_state = final_state
            graph.ticker = request.ticker
            graph._log_state(request.trade_date.isoformat(), final_state)
            decision = graph.process_signal(final_state["final_trade_decision"])

            safe_final_state = self._serialize_final_state(final_state)
            message_logger.flush_final_state(safe_final_state)
            self._update_job(job_id, progress=98)
            self._append_job_log(
                log_path,
                "System",
                f"Graph propagation finished with decision={decision}",
            )

            report_path = save_report_to_disk(
                safe_final_state,
                request.ticker,
                report_dir,
            )
            self._append_job_log(log_path, "System", f"Report saved to {report_path}")
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
            self._append_job_log(
                log_path,
                "Error",
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            )
            self._update_job(
                job_id,
                status=JobStatus.FAILED,
                progress=100,
                error_message=str(exc),
                finished_at=datetime.now(),
            )
            self._persist_job_snapshot(job_id, results_dir)

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
        for snapshot_path in self.reports_root.rglob("job_snapshot.json"):
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
                    "log_path": payload.get("log_path")
                    or str(snapshot_path.parent / "message_tool.log"),
                    "results_dir": payload.get("results_dir")
                    or str(snapshot_path.parent),
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
        self._persist_job_snapshot(job_id)

    def _persist_job_snapshot(
        self,
        job_id: str,
        report_dir: Optional[Path] = None,
    ) -> None:
        with self._lock:
            job_data = self._jobs.get(job_id)
            if not job_data:
                return
            snapshot = dict(job_data)

        snapshot_dir = report_dir
        if snapshot_dir is None:
            if snapshot.get("results_dir"):
                snapshot_dir = Path(snapshot["results_dir"])
            elif snapshot.get("report_path"):
                snapshot_dir = Path(snapshot["report_path"]).parent.parent
            else:
                request = snapshot["request"]
                snapshot_dir = (
                    self.reports_root
                    / request.ticker
                    / request.trade_date.isoformat()
                )
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "job_id": snapshot["job_id"],
            "status": snapshot["status"].value,
            "progress": snapshot["progress"],
            "request": snapshot["request"].model_dump(mode="json"),
            "final_state": snapshot.get("final_state"),
            "decision": snapshot.get("decision"),
            "error_message": snapshot.get("error_message"),
            "report_path": snapshot.get("report_path"),
            "log_path": snapshot.get("log_path"),
            "results_dir": snapshot.get("results_dir"),
            "created_at": snapshot["created_at"].isoformat(),
            "started_at": self._format_optional_datetime(snapshot.get("started_at")),
            "finished_at": self._format_optional_datetime(snapshot.get("finished_at")),
        }
        snapshot_path = snapshot_dir / "job_snapshot.json"
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
    def _append_job_log(log_path: Path, message_type: str, content: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        normalized_content = content.replace("\r\n", "\n").replace("\n", " ")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{timestamp} [{message_type}] {normalized_content}\n")

    @staticmethod
    def _parse_job_log_line(line_no: int, raw_line: str) -> AnalysisJobLogEntry:
        matched = JOB_LOG_PATTERN.match(raw_line)
        if not matched:
            return AnalysisJobLogEntry(
                line_no=line_no,
                timestamp=None,
                level="Raw",
                content=raw_line,
            )

        return AnalysisJobLogEntry(
            line_no=line_no,
            timestamp=datetime.strptime(
                matched.group("timestamp"),
                "%Y-%m-%d %H:%M:%S",
            ),
            level=matched.group("level"),
            content=matched.group("content"),
        )

    @staticmethod
    def _normalize_selected_analysts(selected_analysts: list[Any]) -> list[Any]:
        selected_by_key = {item.value: item for item in selected_analysts}
        return [selected_by_key[key] for key in ANALYST_ORDER if key in selected_by_key]

    def _get_results_dir(self, request: AnalysisJobRequest, job_id: str) -> Path:
        return (
            self.reports_root
            / request.ticker
            / request.trade_date.isoformat()
            / job_id
        )

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
            backend_url=request.backend_url,
            google_thinking_level=request.google_thinking_level,
            openai_reasoning_effort=request.openai_reasoning_effort,
            anthropic_effort=request.anthropic_effort,
            output_language=request.output_language,
            max_debate_rounds=request.max_debate_rounds,
            max_risk_discuss_rounds=request.max_risk_discuss_rounds,
            report_path=snapshot.get("report_path"),
        )

    @staticmethod
    def _build_agent_reports(final_state: Dict[str, Any]) -> list[HistoricalReportAgentGroup]:
        groups: list[HistoricalReportAgentGroup] = []

        analyst_reports = []
        for field_name, title in [
            ("market_report", "市场分析报告"),
            ("sentiment_report", "社交情绪分析报告"),
            ("news_report", "新闻分析报告"),
            ("fundamentals_report", "基本面分析报告"),
        ]:
            content = str(final_state.get(field_name) or "").strip()
            if content:
                analyst_reports.append(
                    HistoricalReportItem(
                        report_key=field_name,
                        title=title,
                        content=content,
                    )
                )
        if analyst_reports:
            groups.append(
                HistoricalReportAgentGroup(
                    agent_key="analyst_team",
                    agent_name="分析师团队",
                    reports=analyst_reports,
                )
            )

        research_reports = []
        investment_plan = str(final_state.get("investment_plan") or "").strip()
        investment_debate_state = final_state.get("investment_debate_state") or {}
        for report_key, field_name, title in [
            ("research_bull", "bull_history", "多方研究报告"),
            ("research_bear", "bear_history", "空方研究报告"),
            ("research_manager", "judge_decision", "研究经理决策报告"),
        ]:
            content = str(investment_debate_state.get(field_name) or "").strip()
            if content and content != investment_plan:
                research_reports.append(
                    HistoricalReportItem(
                        report_key=report_key,
                        title=title,
                        content=content,
                    )
                )
        if investment_plan:
            research_reports.append(
                HistoricalReportItem(
                    report_key="investment_plan",
                    title="研究经理投资计划",
                    content=investment_plan,
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

        trader_plan = str(final_state.get("trader_investment_plan") or "").strip()
        if trader_plan:
            groups.append(
                HistoricalReportAgentGroup(
                    agent_key="trading_desk",
                    agent_name="交易台",
                    reports=[
                        HistoricalReportItem(
                            report_key="trader_investment_plan",
                            title="交易员执行方案",
                            content=trader_plan,
                        )
                    ],
                )
            )

        risk_reports = []
        risk_debate_state = final_state.get("risk_debate_state") or {}
        final_trade_decision = str(
            final_state.get("final_trade_decision") or ""
        ).strip()
        for report_key, field_name, title in [
            ("risk_aggressive", "aggressive_history", "激进风险分析报告"),
            ("risk_conservative", "conservative_history", "保守风险分析报告"),
            ("risk_neutral", "neutral_history", "中性风险分析报告"),
        ]:
            content = str(risk_debate_state.get(field_name) or "").strip()
            if content and content != final_trade_decision:
                risk_reports.append(
                    HistoricalReportItem(
                        report_key=report_key,
                        title=title,
                        content=content,
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

        portfolio_manager_decision = str(
            risk_debate_state.get("judge_decision") or ""
        ).strip()
        verdict_content = final_trade_decision or portfolio_manager_decision
        if verdict_content:
            groups.append(
                HistoricalReportAgentGroup(
                    agent_key="final_verdict",
                    agent_name="最终裁决",
                    reports=[
                        HistoricalReportItem(
                            report_key="final_trade_decision",
                            title="最终交易决策",
                            content=verdict_content,
                        )
                    ],
                )
            )

        return groups


class _StreamingMessageLogger:
    def __init__(self, log_path: Path, selected_analysts: list[str]) -> None:
        self.log_path = log_path
        self.selected_analysts = selected_analysts
        self._last_message_id = None
        self._completed_sections = set()

    def process_chunk(self, chunk: Dict[str, Any]) -> int:
        messages = chunk.get("messages") or []
        if messages:
            last_message = messages[-1]
            message_key = self._build_message_key(last_message)
            if message_key != self._last_message_id:
                self._last_message_id = message_key
                message_type, content = self._classify_message(last_message)
                if content:
                    AnalysisJobManager._append_job_log(
                        self.log_path,
                        message_type,
                        content,
                    )
                self._append_tool_calls(last_message)

        self._update_report_progress(chunk)
        return self._calculate_progress()

    def flush_final_state(self, final_state: Dict[str, Any]) -> None:
        self._update_report_progress(final_state)
        AnalysisJobManager._append_job_log(
            self.log_path,
            "System",
            "Final report sections persisted from terminal graph state",
        )

    def _append_tool_calls(self, message: Any) -> None:
        tool_calls = getattr(message, "tool_calls", None) or []
        for tool_call in tool_calls:
            if isinstance(tool_call, dict):
                tool_name = tool_call.get("name", "unknown_tool")
                tool_args = tool_call.get("args", {})
            else:
                tool_name = getattr(tool_call, "name", "unknown_tool")
                tool_args = getattr(tool_call, "args", {})
            args_text = ", ".join(f"{key}={value}" for key, value in tool_args.items())
            AnalysisJobManager._append_job_log(
                self.log_path,
                "Tool Call",
                f"{tool_name}({args_text})",
            )

    def _update_report_progress(self, state: Dict[str, Any]) -> None:
        for report_key in [
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
        ]:
            if state.get(report_key):
                self._completed_sections.add(report_key)

    def _calculate_progress(self) -> int:
        weights = ["investment_plan", "trader_investment_plan", "final_trade_decision"]
        weights.extend(
            f"{analyst}_report" if analyst != "social" else "sentiment_report"
            for analyst in self.selected_analysts
        )
        progress = 5
        for section in self._completed_sections:
            if section in weights:
                progress += REPORT_PROGRESS_WEIGHTS.get(section, 0)
        return min(progress, 95)

    @classmethod
    def _classify_message(cls, message: Any) -> tuple[str, Optional[str]]:
        content = cls._extract_content_string(getattr(message, "content", None))
        if isinstance(message, HumanMessage):
            if content and content.strip() == "Continue":
                return "Control", content
            return "User", content
        if isinstance(message, ToolMessage):
            return "Data", content
        if isinstance(message, AIMessage):
            return "Agent", content
        return "System", content

    @staticmethod
    def _build_message_key(message: Any) -> str:
        message_id = getattr(message, "id", None)
        if message_id:
            return str(message_id)
        return (
            f"{type(message).__name__}:"
            f"{repr(getattr(message, 'content', None))}:"
            f"{repr(getattr(message, 'tool_call_id', None))}:"
            f"{repr(getattr(message, 'tool_calls', None))}"
        )

    @staticmethod
    def _extract_content_string(content: Any) -> Optional[str]:
        if content is None:
            return None
        if isinstance(content, str):
            stripped = content.strip()
            return stripped or None
        if isinstance(content, dict):
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
            return None
        if isinstance(content, list):
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = str(item.get("text", "")).strip()
                elif isinstance(item, str):
                    text = item.strip()
                else:
                    text = ""
                if text:
                    text_parts.append(text)
            result = " ".join(text_parts).strip()
            return result or None
        result = str(content).strip()
        return result or None
