from __future__ import annotations

import time
import traceback
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.web.analysis.manager import AnalysisJobManager
from tradingagents.web.market_monitor.persistence import MarketMonitorPersistence
from tradingagents.web.market_monitor.pipeline import MarketMonitorPipeline
from tradingagents.web.market_monitor.schemas import (
    HistoricalMarketMonitorRunDetail,
    HistoricalMarketMonitorRunSummary,
    MarketMonitorDataStatusResponse,
    MarketMonitorFactSheet,
    MarketMonitorHistoryRequest,
    MarketMonitorHistoryResponse,
    MarketMonitorPromptTrace,
    MarketMonitorRunManifest,
    MarketMonitorRunRequest,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
    MarketMonitorStageResult,
)
from tradingagents.web.market_monitor.service import MarketMonitorRunService
from tradingagents.web.market_monitor.snapshot_service import MarketMonitorSnapshotService
from tradingagents.web.market_monitor.trading_calendar import resolve_market_monitor_as_of_date
from tradingagents.web.schemas import AnalysisJobLogEntry, JobStatus


RECOVERABLE_STAGE_STATUSES = {JobStatus.PENDING, JobStatus.RUNNING}


class MarketMonitorRunManager:
    def __init__(
        self,
        runs_root: Path | None = None,
        service: MarketMonitorSnapshotService | None = None,
    ) -> None:
        self.runs_root = runs_root or Path(DEFAULT_CONFIG["results_dir"]) / "market_monitor"
        self.service = service or MarketMonitorSnapshotService()
        self._runs: dict[str, dict[str, Any]] = {}
        self._futures: dict[str, Future] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="market-monitor-run")
        self._restore_persisted_runs()

    def run_snapshot(
        self,
        request: MarketMonitorSnapshotRequest,
    ) -> HistoricalMarketMonitorRunDetail:
        run_request = MarketMonitorRunRequest(
            trigger_endpoint="snapshot",
            as_of_date=request.as_of_date,
            force_refresh=request.force_refresh,
            data_mode=request.data_mode,
            mode="snapshot",
        )
        return self.create_run(run_request)

    def run_history(
        self,
        request: MarketMonitorHistoryRequest,
    ) -> HistoricalMarketMonitorRunDetail:
        run_request = MarketMonitorRunRequest(
            trigger_endpoint="history",
            as_of_date=request.as_of_date,
            days=request.days,
            force_refresh=request.force_refresh,
            data_mode=request.data_mode,
            mode="history",
        )
        return self.create_run(run_request)

    def run_data_status(
        self,
        request: MarketMonitorSnapshotRequest,
    ) -> HistoricalMarketMonitorRunDetail:
        run_request = MarketMonitorRunRequest(
            trigger_endpoint="data_status",
            as_of_date=request.as_of_date,
            force_refresh=request.force_refresh,
            data_mode=request.data_mode,
            mode="data_status",
        )
        return self.create_run(run_request)

    def create_run(self, request: MarketMonitorRunRequest) -> HistoricalMarketMonitorRunDetail:
        request = self._resolve_request_as_of_date(request)
        run_id, _, _, _ = self._prepare_run(request)
        future = self._executor.submit(self._execute_prepared_run, request, run_id)
        with self._lock:
            self._futures[run_id] = future
        future.add_done_callback(lambda _: self._forget_future(run_id))
        return self.get_historical_run(run_id)

    def _resolve_request_as_of_date(self, request: MarketMonitorRunRequest) -> MarketMonitorRunRequest:
        as_of_date = resolve_market_monitor_as_of_date(request.as_of_date, request.data_mode)
        return request.model_copy(update={"as_of_date": as_of_date})

    def _resolve_service(self, request: MarketMonitorRunRequest) -> MarketMonitorSnapshotService:
        if request.llm_config is not None:
            return MarketMonitorSnapshotService(llm_config=request.llm_config)
        return self.service

    def list_historical_runs(self) -> list[HistoricalMarketMonitorRunSummary]:
        with self._lock:
            snapshots = [dict(run_data) for run_data in self._runs.values()]
        summaries = [self._build_summary(snapshot) for snapshot in snapshots]
        return sorted(summaries, key=lambda item: item.generated_at, reverse=True)

    def get_historical_run(self, run_id: str) -> HistoricalMarketMonitorRunDetail:
        snapshot = self._get_run_snapshot(run_id)
        return HistoricalMarketMonitorRunDetail(
            **self._build_summary(snapshot).model_dump(),
            request=snapshot["request"],
            created_at=snapshot["created_at"],
            started_at=snapshot.get("started_at"),
            finished_at=snapshot.get("finished_at"),
            snapshot=snapshot.get("snapshot"),
            history=snapshot.get("history"),
            data_status=snapshot.get("data_status"),
            fact_sheet=snapshot.get("fact_sheet"),
            manifest=snapshot.get("manifest"),
            stage_results=list(snapshot.get("stage_results") or []),
            prompt_traces=list(snapshot.get("prompt_traces") or []),
        )

    def list_run_logs(self, run_id: str) -> list[AnalysisJobLogEntry]:
        snapshot = self._get_run_snapshot(run_id)
        log_path = Path(snapshot.get("log_path") or Path(snapshot["results_dir"]) / "market_monitor.log")
        if not log_path.exists():
            return []
        entries: list[AnalysisJobLogEntry] = []
        for line_no, raw_line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
            entries.append(AnalysisJobManager._parse_job_log_line(line_no, raw_line))
        return entries

    def _append_run_log(self, log_path: Path, message: str, level: str = "System") -> None:
        AnalysisJobManager._append_job_log(log_path, level, message)

    def _append_run_warning(self, log_path: Path, message: str) -> None:
        self._append_run_log(log_path, message, "Warning")

    def _append_run_error(self, log_path: Path, message: str) -> None:
        self._append_run_log(log_path, message, "Error")

    def list_prompt_traces(self, run_id: str) -> list[MarketMonitorPromptTrace]:
        snapshot = self._get_run_snapshot(run_id)
        traces = snapshot.get("prompt_traces")
        if traces is not None:
            return list(traces)
        persistence = MarketMonitorPersistence(Path(snapshot["results_dir"]))
        return persistence.list_prompt_traces()

    def read_artifact_payload(self, run_id: str, artifact_name: str) -> dict[str, Any]:
        snapshot = self._get_run_snapshot(run_id)
        persistence = MarketMonitorPersistence(Path(snapshot["results_dir"]))
        if artifact_name in {"snapshot", "history", "data_status", "fact_sheet"}:
            artifact_path = persistence.artifact_path(artifact_name)
        elif artifact_name.startswith("history_snapshot_") or artifact_name.startswith("history_fact_sheet_"):
            artifact_path = persistence.artifact_path(artifact_name)
        else:
            raise ValueError(f"Unsupported artifact: {artifact_name}")
        if not artifact_path.exists():
            raise FileNotFoundError(str(artifact_path))
        return persistence.read_artifact_payload(artifact_name)

    def recover_run(self, run_id: str) -> HistoricalMarketMonitorRunDetail:
        snapshot = self._get_run_snapshot(run_id)
        manifest: MarketMonitorRunManifest | None = snapshot.get("manifest")
        if manifest is None or not manifest.recoverable:
            raise ValueError("Market monitor run is not recoverable")
        request: MarketMonitorRunRequest = self._resolve_request_as_of_date(snapshot["request"])
        persistence = MarketMonitorPersistence(Path(snapshot["results_dir"]))
        log_path = Path(snapshot["log_path"])
        reset_stages = [MarketMonitorStageResult(stage_name=stage.stage_name) for stage in manifest.stage_results]
        self._update_run(
            run_id,
            status=JobStatus.PENDING,
            error_message=None,
            started_at=None,
            finished_at=None,
            stage_results=reset_stages,
            snapshot=None,
            history=None,
            data_status=None,
            fact_sheet=None,
            prompt_traces=[],
        )
        self._sync_manifest(run_id, persistence)
        self._append_run_log(log_path, f"恢复运行已提交：run_id={run_id}")
        future = self._executor.submit(self._execute_prepared_run, request, run_id)
        with self._lock:
            self._futures[run_id] = future
        future.add_done_callback(lambda _: self._forget_future(run_id))
        return self.get_historical_run(run_id)

    def _execute_run(
        self,
        request: MarketMonitorRunRequest,
        existing_run_id: str | None = None,
        results_dir: Path | None = None,
    ) -> tuple[
        str,
        MarketMonitorSnapshotResponse | None,
        MarketMonitorHistoryResponse | None,
        MarketMonitorDataStatusResponse | None,
    ]:
        request = self._resolve_request_as_of_date(request)
        run_id, _, _, _ = self._prepare_run(request, existing_run_id=existing_run_id, results_dir=results_dir, start_immediately=True)
        return self._execute_prepared_run(request, run_id)

    def _prepare_run(
        self,
        request: MarketMonitorRunRequest,
        existing_run_id: str | None = None,
        results_dir: Path | None = None,
        start_immediately: bool = False,
    ) -> tuple[str, date, Path, Path]:
        request = self._resolve_request_as_of_date(request)
        run_id = existing_run_id or uuid4().hex
        as_of_date = request.as_of_date
        if existing_run_id is not None:
            snapshot = self._get_run_snapshot(existing_run_id)
            actual_results_dir = results_dir or Path(snapshot["results_dir"])
            log_path = Path(snapshot["log_path"])
            if start_immediately:
                self._update_run(run_id, status=JobStatus.RUNNING, started_at=datetime.now(), error_message=None, finished_at=None)
                self._sync_manifest(run_id, MarketMonitorPersistence(actual_results_dir))
            return run_id, as_of_date, actual_results_dir, log_path

        actual_results_dir = results_dir or self._get_results_dir(as_of_date, run_id)
        persistence = MarketMonitorPersistence(actual_results_dir)
        persistence.ensure_layout()
        log_path = actual_results_dir / "market_monitor.log"
        created_at = datetime.now()
        stage_names = ["request_received", "artifact_generation"]
        if request.trigger_endpoint == "history":
            stage_names = ["request_received", "history_materialization", "artifact_generation"]
        stage_results = [MarketMonitorStageResult(stage_name=name) for name in stage_names]
        manifest = MarketMonitorRunManifest(
            run_id=run_id,
            mode=request.mode or request.trigger_endpoint,
            request=request,
            status=JobStatus.PENDING,
            created_at=created_at,
            results_dir=str(actual_results_dir),
            log_path=str(log_path),
            llm_config=request.llm_config,
            stage_results=stage_results,
        )
        persistence.write_manifest(manifest)
        run_data = {
            "run_id": run_id,
            "request": request,
            "status": JobStatus.PENDING,
            "snapshot": None,
            "history": None,
            "data_status": None,
            "fact_sheet": None,
            "manifest": manifest,
            "stage_results": stage_results,
            "prompt_traces": [],
            "error_message": None,
            "log_path": str(log_path),
            "results_dir": str(actual_results_dir),
            "created_at": created_at,
            "started_at": None,
            "finished_at": None,
        }
        with self._lock:
            self._runs[run_id] = run_data
        if start_immediately:
            self._update_run(run_id, status=JobStatus.RUNNING, started_at=datetime.now())
            self._sync_manifest(run_id, persistence)
        return run_id, as_of_date, actual_results_dir, log_path

    def _execute_prepared_run(
        self,
        request: MarketMonitorRunRequest,
        run_id: str,
    ) -> tuple[
        str,
        MarketMonitorSnapshotResponse | None,
        MarketMonitorHistoryResponse | None,
        MarketMonitorDataStatusResponse | None,
    ]:
        snapshot = self._get_run_snapshot(run_id)
        actual_results_dir = Path(snapshot["results_dir"])
        persistence = MarketMonitorPersistence(actual_results_dir)
        persistence.ensure_layout()
        log_path = Path(snapshot["log_path"])
        request = self._resolve_request_as_of_date(request)
        as_of_date = request.as_of_date
        self._update_run(run_id, request=request)
        started_perf = time.perf_counter()
        if snapshot.get("status") != JobStatus.RUNNING:
            self._update_run(run_id, status=JobStatus.RUNNING, started_at=datetime.now(), error_message=None, finished_at=None)
        self._set_stage_status(run_id, persistence, "request_received", "completed")
        self._sync_manifest(run_id, persistence)
        self._append_run_log(
            log_path,
            (
                f"运行已开始：入口={request.trigger_endpoint}，美东交易日={as_of_date.isoformat()}，"
                f"历史天数={request.days or 20}，force_refresh={str(request.force_refresh).lower()}，数据模式={request.data_mode}"
            ),
        )
        try:
            service = self._resolve_service(request)
            llm_config = request.llm_config
            provider = llm_config.provider if llm_config and llm_config.provider else DEFAULT_CONFIG["llm_provider"]
            model = llm_config.model if llm_config and llm_config.model else DEFAULT_CONFIG["deep_think_llm"]
            effort = llm_config.reasoning_effort if llm_config and llm_config.reasoning_effort else "默认"
            source = "请求配置" if llm_config is not None else "默认配置"
            self._append_run_log(log_path, f"已初始化市场监控服务：配置来源={source}，provider={provider}，model={model}，reasoning_effort={effort}")
            run_service = MarketMonitorRunService(
                service,
                MarketMonitorPipeline(),
            )
            self._append_run_log(log_path, "阶段开始：生成市场监控产物")
            self._set_stage_status(run_id, persistence, "artifact_generation", "running")
            if request.trigger_endpoint == "history":
                self._append_run_log(log_path, "阶段开始：历史回放日期解析与快照生成")
                self._set_stage_status(run_id, persistence, "history_materialization", "running")
            previous_snapshots = self._previous_completed_snapshots(as_of_date, exclude_run_id=run_id)
            self._append_run_log(log_path, f"已加载历史上下文：可用快照 {len(previous_snapshots)} 条")
            execution = run_service.execute(
                request,
                run_id,
                previous_snapshots=previous_snapshots,
                log=lambda message: self._append_run_log(log_path, message),
            )
            if execution.snapshot is not None:
                self._append_run_log(log_path, "开始写入单日快照产物")
                if execution.fact_sheet is not None:
                    persistence.write_fact_sheet_artifact(execution.fact_sheet)
                    self._append_run_log(log_path, "事实表产物写入完成")
                for trace in execution.prompt_traces:
                    persistence.write_prompt_trace(f"{trace.stage}_{trace.card_type or 'general'}", trace)
                self._append_run_log(log_path, f"Prompt trace 写入完成：{len(execution.prompt_traces)} 条")
                persistence.write_snapshot_artifact(execution.snapshot)
                self._append_run_log(
                    log_path,
                    (
                        "快照产物写入完成："
                        f"Prompt trace {len(execution.prompt_traces)} 条，"
                        f"缺失数据 {len(execution.snapshot.missing_data)} 项，"
                        f"开放缺口 {len(execution.snapshot.fact_sheet.open_gaps if execution.snapshot.fact_sheet else [])} 项"
                    ),
                )
            elif execution.history is not None:
                self._append_run_log(log_path, "开始写入历史回放产物")
                for index, history_snapshot in enumerate(execution.history_snapshots, start=1):
                    suffix = history_snapshot.as_of_date.isoformat()
                    persistence.write_artifact_payload(
                        f"history_snapshot_{suffix}",
                        history_snapshot.model_dump(mode="json"),
                    )
                    if history_snapshot.fact_sheet is not None:
                        persistence.write_artifact_payload(
                            f"history_fact_sheet_{suffix}",
                            history_snapshot.fact_sheet.model_dump(mode="json"),
                        )
                    for trace in history_snapshot.prompt_traces:
                        persistence.write_prompt_trace(f"history_{suffix}_{trace.card_type or trace.stage}", trace)
                    self._append_run_log(
                        log_path,
                        f"历史快照已落盘：{index}/{len(execution.history_snapshots)}，美东交易日={suffix}，Prompt trace {len(history_snapshot.prompt_traces)} 条，缺失数据 {len(history_snapshot.missing_data)} 项",
                    )
                persistence.write_history_artifact(execution.history)
                self._set_stage_status(run_id, persistence, "history_materialization", "completed")
                self._append_run_log(log_path, "阶段完成：历史回放产物写入")
                self._append_run_log(log_path, f"历史产物写入完成：点位 {len(execution.history.points)} 个，历史快照 {len(execution.history_snapshots)} 个")
            elif execution.data_status is not None:
                self._append_run_log(log_path, "开始写入数据状态产物")
                if execution.fact_sheet is not None:
                    persistence.write_fact_sheet_artifact(execution.fact_sheet)
                    self._append_run_log(log_path, "事实表产物写入完成")
                persistence.write_data_status_artifact(execution.data_status)
                self._append_run_log(
                    log_path,
                    (
                        "数据状态产物写入完成："
                        f"缺失数据 {len(execution.data_status.missing_data)} 项，"
                        f"开放缺口 {len(execution.data_status.open_gaps)} 项，"
                        f"风险提示 {len(execution.data_status.risks)} 项"
                    ),
                )
            self._set_stage_status(run_id, persistence, "artifact_generation", "completed")
            self._append_run_log(log_path, "阶段完成：生成市场监控产物")
            elapsed_ms = int((time.perf_counter() - started_perf) * 1000)
            self._append_run_log(log_path, f"运行已完成：状态=completed，总耗时={elapsed_ms}ms")
            self._update_run(
                run_id,
                status=JobStatus.COMPLETED,
                snapshot=execution.snapshot,
                history=execution.history,
                data_status=execution.data_status,
                fact_sheet=execution.fact_sheet,
                prompt_traces=execution.prompt_traces,
                finished_at=datetime.now(),
            )
            self._sync_manifest(run_id, persistence)
            return run_id, execution.snapshot, execution.history, execution.data_status
        except Exception as exc:
            if request.trigger_endpoint == "history":
                self._set_stage_status(run_id, persistence, "history_materialization", "failed", error=str(exc))
            self._set_stage_status(run_id, persistence, "artifact_generation", "failed", error=str(exc))
            elapsed_ms = int((time.perf_counter() - started_perf) * 1000)
            self._append_run_error(log_path, f"运行失败：{type(exc).__name__}: {exc}，耗时={elapsed_ms}ms")
            self._append_run_error(log_path, traceback.format_exc())
            self._update_run(
                run_id,
                status=JobStatus.FAILED,
                error_message=str(exc),
                finished_at=datetime.now(),
            )
            self._sync_manifest(run_id, persistence, recoverable=True)
            raise

    def _forget_future(self, run_id: str) -> None:
        with self._lock:
            self._futures.pop(run_id, None)

    def _get_run_snapshot(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            run_data = self._runs.get(run_id)
            if run_data is None:
                raise KeyError(run_id)
            return dict(run_data)

    def _update_run(self, run_id: str, **changes: Any) -> None:
        with self._lock:
            if run_id in self._runs:
                self._runs[run_id].update(changes)

    def _previous_completed_snapshots(
        self,
        as_of_date: date,
        *,
        exclude_run_id: str | None = None,
        limit: int = 5,
    ) -> list[MarketMonitorSnapshotResponse]:
        with self._lock:
            snapshots = [
                run_data["snapshot"]
                for run_id, run_data in self._runs.items()
                if run_id != exclude_run_id
                and run_data.get("status") == JobStatus.COMPLETED
                and run_data.get("snapshot") is not None
                and run_data["snapshot"].as_of_date <= as_of_date
            ]
        snapshots.sort(key=lambda snapshot: (snapshot.as_of_date, snapshot.timestamp))
        return snapshots[-limit:]

    def _restore_persisted_runs(self) -> None:
        self.runs_root.mkdir(parents=True, exist_ok=True)
        for manifest_path in self.runs_root.rglob("manifest.json"):
            try:
                persistence = MarketMonitorPersistence(manifest_path.parent)
                manifest = persistence.read_manifest()
                if manifest.status in RECOVERABLE_STAGE_STATUSES:
                    manifest = manifest.model_copy(
                        update={
                            "status": JobStatus.FAILED,
                            "recoverable": True,
                            "finished_at": manifest.finished_at or datetime.now(),
                            "error_message": manifest.error_message or "Run interrupted before completion",
                            "stage_results": self._mark_interrupted_stages(manifest.stage_results),
                        }
                    )
                    persistence.write_manifest(manifest)
                snapshot = persistence.read_snapshot_artifact() if persistence.artifact_path("snapshot").exists() else None
                history = persistence.read_history_artifact() if persistence.artifact_path("history").exists() else None
                data_status = persistence.read_data_status_artifact() if persistence.artifact_path("data_status").exists() else None
                fact_sheet = persistence.read_fact_sheet_artifact() if persistence.artifact_path("fact_sheet").exists() else None
                run_data = {
                    "run_id": manifest.run_id,
                    "request": manifest.request,
                    "status": manifest.status,
                    "snapshot": snapshot,
                    "history": history,
                    "data_status": data_status,
                    "fact_sheet": fact_sheet,
                    "manifest": manifest,
                    "stage_results": list(manifest.stage_results),
                    "prompt_traces": persistence.list_prompt_traces(),
                    "error_message": manifest.error_message,
                    "log_path": manifest.log_path,
                    "results_dir": manifest.results_dir,
                    "created_at": manifest.created_at,
                    "started_at": manifest.started_at,
                    "finished_at": manifest.finished_at,
                }
            except Exception:
                continue
            self._runs[run_data["run_id"]] = run_data

    def _mark_interrupted_stages(
        self,
        stage_results: list[MarketMonitorStageResult],
    ) -> list[MarketMonitorStageResult]:
        updated: list[MarketMonitorStageResult] = []
        now = datetime.now()
        for stage in stage_results:
            current = stage.model_copy()
            if current.status in {"pending", "running"}:
                if current.started_at is None:
                    current.started_at = now
                current.finished_at = now
                current.status = "failed"
                current.error = current.error or "Run interrupted before completion"
            updated.append(current)
        return updated

    def _set_stage_status(
        self,
        run_id: str,
        persistence: MarketMonitorPersistence,
        stage_name: str,
        status: str,
        error: str | None = None,
    ) -> None:
        snapshot = self._get_run_snapshot(run_id)
        updated: list[MarketMonitorStageResult] = []
        now = datetime.now()
        for stage in snapshot.get("stage_results") or []:
            current = stage.model_copy()
            if current.stage_name == stage_name:
                if status == "running" and current.started_at is None:
                    current.started_at = now
                if status in {"completed", "failed", "skipped"}:
                    if current.started_at is None:
                        current.started_at = now
                    current.finished_at = now
                current.status = status
                current.error = error
                stage_payload = current.model_dump(mode="json")
                persistence.write_stage_result(current, payload={"stage": stage_payload})
            updated.append(current)
        self._update_run(run_id, stage_results=updated)

    def _sync_manifest(
        self,
        run_id: str,
        persistence: MarketMonitorPersistence,
        recoverable: bool = False,
    ) -> None:
        snapshot = self._get_run_snapshot(run_id)
        manifest = MarketMonitorRunManifest(
            run_id=snapshot["run_id"],
            mode=snapshot["request"].mode or snapshot["request"].trigger_endpoint,
            request=snapshot["request"],
            status=snapshot["status"],
            created_at=snapshot["created_at"],
            started_at=snapshot.get("started_at"),
            finished_at=snapshot.get("finished_at"),
            results_dir=snapshot["results_dir"],
            log_path=snapshot["log_path"],
            error_message=snapshot.get("error_message"),
            recoverable=recoverable or bool(snapshot.get("error_message")),
            llm_config=snapshot["request"].llm_config,
            stage_results=list(snapshot.get("stage_results") or []),
            artifact_paths={
                artifact_path.stem: str(artifact_path)
                for artifact_path in sorted(persistence.artifacts_dir.glob("*.json"))
            },
            prompt_trace_count=len(snapshot.get("prompt_traces") or []),
        )
        persistence.write_manifest(manifest)
        self._update_run(run_id, manifest=manifest)

    def _build_summary(self, snapshot: dict[str, Any]) -> HistoricalMarketMonitorRunSummary:
        response: MarketMonitorSnapshotResponse | None = snapshot.get("snapshot")
        data_status: MarketMonitorDataStatusResponse | None = snapshot.get("data_status")
        manifest: MarketMonitorRunManifest | None = snapshot.get("manifest")
        as_of_date = (
            response.as_of_date
            if response is not None
            else data_status.as_of_date
            if data_status is not None
            else snapshot["request"].as_of_date or snapshot["created_at"].date()
        )
        return HistoricalMarketMonitorRunSummary(
            run_id=snapshot["run_id"],
            trigger_endpoint=snapshot["request"].trigger_endpoint,
            as_of_date=as_of_date,
            days=snapshot["request"].days,
            status=snapshot["status"],
            generated_at=snapshot.get("finished_at") or snapshot.get("started_at") or snapshot["created_at"],
            data_freshness=response.data_freshness if response is not None else data_status.data_freshness if data_status is not None else None,
            regime_label=response.execution_card.regime_label if response is not None else None,
            degraded=bool(data_status.missing_data if data_status is not None else response.missing_data if response is not None else False),
            recoverable=manifest.recoverable if manifest is not None else False,
            error_message=snapshot.get("error_message"),
            log_path=snapshot.get("log_path"),
            results_dir=snapshot.get("results_dir"),
        )

    def _get_results_dir(self, as_of_date: date, run_id: str) -> Path:
        return self.runs_root / as_of_date.isoformat() / run_id
