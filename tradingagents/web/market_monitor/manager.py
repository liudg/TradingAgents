from __future__ import annotations

import traceback
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.web.analysis.manager import AnalysisJobManager
from tradingagents.web.market_monitor.persistence import MarketMonitorPersistence
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
from tradingagents.web.market_monitor.snapshot_service import MarketMonitorSnapshotService
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
        self._lock = Lock()
        self._restore_persisted_runs()

    def run_snapshot(
        self,
        request: MarketMonitorSnapshotRequest,
    ) -> MarketMonitorSnapshotResponse:
        run_request = MarketMonitorRunRequest(
            trigger_endpoint="snapshot",
            as_of_date=request.as_of_date,
            force_refresh=request.force_refresh,
            mode="snapshot",
        )
        snapshot, _, _ = self._execute_run(run_request)
        if snapshot is None:
            raise RuntimeError("snapshot payload missing")
        return snapshot

    def run_history(
        self,
        request: MarketMonitorHistoryRequest,
    ) -> MarketMonitorHistoryResponse:
        run_request = MarketMonitorRunRequest(
            trigger_endpoint="history",
            as_of_date=request.as_of_date,
            days=request.days,
            force_refresh=request.force_refresh,
            mode="history",
        )
        _, history, _ = self._execute_run(run_request)
        if history is None:
            raise RuntimeError("history payload missing")
        return history

    def run_data_status(
        self,
        request: MarketMonitorSnapshotRequest,
    ) -> MarketMonitorDataStatusResponse:
        run_request = MarketMonitorRunRequest(
            trigger_endpoint="data_status",
            as_of_date=request.as_of_date,
            force_refresh=request.force_refresh,
            mode="data_status",
        )
        _, _, data_status = self._execute_run(run_request)
        if data_status is None:
            raise RuntimeError("data status payload missing")
        return data_status

    def _resolve_service(self, request: MarketMonitorRunRequest) -> MarketMonitorSnapshotService:
        if request.llm_config is not None:
            return MarketMonitorSnapshotService(llm_config=request.llm_config)
        return self.service

    def list_historical_runs(self) -> list[HistoricalMarketMonitorRunSummary]:
        with self._lock:
            snapshots = [
                dict(run_data)
                for run_data in self._runs.values()
                if run_data.get("status") in {JobStatus.COMPLETED, JobStatus.FAILED}
            ]
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
        request: MarketMonitorRunRequest = snapshot["request"]
        service = self._resolve_service(request)
        persistence = MarketMonitorPersistence(Path(snapshot["results_dir"]))
        log_path = Path(snapshot["log_path"])
        started_at = datetime.now()
        self._update_run(
            run_id,
            status=JobStatus.RUNNING,
            error_message=None,
            started_at=started_at,
            finished_at=None,
        )
        reset_stages = [MarketMonitorStageResult(stage_name=stage.stage_name) for stage in manifest.stage_results]
        self._update_run(run_id, stage_results=reset_stages)
        self._set_stage_status(run_id, persistence, "request_received", "completed")
        self._sync_manifest(run_id, persistence)
        AnalysisJobManager._append_job_log(log_path, "System", f"Recovering market monitor run {run_id}")
        try:
            if request.trigger_endpoint == "snapshot":
                snapshot_request = MarketMonitorSnapshotRequest(
                    as_of_date=request.as_of_date,
                    force_refresh=request.force_refresh,
                )
                self._set_stage_status(run_id, persistence, "artifact_generation", "running")
                recovered_snapshot = service.get_snapshot(snapshot_request).model_copy(update={"run_id": run_id})
                if recovered_snapshot.fact_sheet is not None:
                    persistence.write_fact_sheet_artifact(recovered_snapshot.fact_sheet)
                for trace in recovered_snapshot.prompt_traces:
                    persistence.write_prompt_trace(f"{trace.stage}_{trace.card_type or 'general'}", trace)
                persistence.write_snapshot_artifact(recovered_snapshot)
                self._set_stage_status(run_id, persistence, "artifact_generation", "completed")
                self._update_run(
                    run_id,
                    status=JobStatus.COMPLETED,
                    snapshot=recovered_snapshot,
                    history=None,
                    data_status=None,
                    fact_sheet=recovered_snapshot.fact_sheet,
                    prompt_traces=recovered_snapshot.prompt_traces,
                    finished_at=datetime.now(),
                )
            elif request.trigger_endpoint == "data_status":
                snapshot_request = MarketMonitorSnapshotRequest(
                    as_of_date=request.as_of_date,
                    force_refresh=request.force_refresh,
                )
                self._set_stage_status(run_id, persistence, "artifact_generation", "running")
                recovered_data_status = service.get_data_status(snapshot_request).model_copy(update={"run_id": run_id})
                if recovered_data_status.fact_sheet is not None:
                    persistence.write_fact_sheet_artifact(recovered_data_status.fact_sheet)
                persistence.write_data_status_artifact(recovered_data_status)
                self._set_stage_status(run_id, persistence, "artifact_generation", "completed")
                self._update_run(
                    run_id,
                    status=JobStatus.COMPLETED,
                    snapshot=None,
                    history=None,
                    data_status=recovered_data_status,
                    fact_sheet=recovered_data_status.fact_sheet,
                    prompt_traces=[],
                    finished_at=datetime.now(),
                )
            else:
                history_request = MarketMonitorHistoryRequest(
                    as_of_date=request.as_of_date,
                    days=request.days or 20,
                    force_refresh=request.force_refresh,
                )
                self._set_stage_status(run_id, persistence, "artifact_generation", "running")
                self._set_stage_status(run_id, persistence, "history_materialization", "running")
                trade_dates = service.resolve_history_trade_dates(history_request)
                history_snapshots: list[MarketMonitorSnapshotResponse] = []
                prompt_traces: list[MarketMonitorPromptTrace] = []
                latest_fact_sheet: MarketMonitorFactSheet | None = None
                for trade_date in trade_dates:
                    suffix = trade_date.isoformat()
                    artifact_name = f"history_snapshot_{suffix}"
                    artifact_path = persistence.artifact_path(artifact_name)
                    if artifact_path.exists():
                        payload = persistence.read_artifact_payload(artifact_name)
                        history_snapshot = MarketMonitorSnapshotResponse.model_validate(payload)
                    else:
                        snapshot_request = MarketMonitorSnapshotRequest(
                            as_of_date=trade_date,
                            force_refresh=request.force_refresh,
                        )
                        history_snapshot = service.get_snapshot(snapshot_request).model_copy(update={"run_id": run_id})
                        persistence.write_artifact_payload(artifact_name, history_snapshot.model_dump(mode="json"))
                        if history_snapshot.fact_sheet is not None:
                            persistence.write_artifact_payload(
                                f"history_fact_sheet_{suffix}",
                                history_snapshot.fact_sheet.model_dump(mode="json"),
                            )
                        for trace in history_snapshot.prompt_traces:
                            persistence.write_prompt_trace(f"history_{suffix}_{trace.card_type or trace.stage}", trace)
                    history_snapshots.append(history_snapshot)
                    prompt_traces.extend(history_snapshot.prompt_traces)
                    if history_snapshot.fact_sheet is not None:
                        latest_fact_sheet = history_snapshot.fact_sheet
                recovered_history = service.build_history_response(
                    history_request.as_of_date or date.today(),
                    history_snapshots,
                ).model_copy(update={"run_id": run_id})
                persistence.write_history_artifact(recovered_history)
                self._set_stage_status(run_id, persistence, "history_materialization", "completed")
                self._set_stage_status(run_id, persistence, "artifact_generation", "completed")
                self._update_run(
                    run_id,
                    status=JobStatus.COMPLETED,
                    snapshot=None,
                    history=recovered_history,
                    data_status=None,
                    fact_sheet=latest_fact_sheet,
                    prompt_traces=prompt_traces,
                    finished_at=datetime.now(),
                )
            self._sync_manifest(run_id, persistence)
            return self.get_historical_run(run_id)
        except Exception as exc:
            if request.trigger_endpoint == "history":
                self._set_stage_status(run_id, persistence, "history_materialization", "failed", error=str(exc))
            self._set_stage_status(run_id, persistence, "artifact_generation", "failed", error=str(exc))
            self._update_run(
                run_id,
                status=JobStatus.FAILED,
                error_message=str(exc),
                finished_at=datetime.now(),
            )
            self._sync_manifest(run_id, persistence, recoverable=True)
            raise

    def _execute_run(
        self,
        request: MarketMonitorRunRequest,
    ) -> tuple[
        MarketMonitorSnapshotResponse | None,
        MarketMonitorHistoryResponse | None,
        MarketMonitorDataStatusResponse | None,
    ]:
        service = self._resolve_service(request)
        run_id = uuid4().hex
        as_of_date = request.as_of_date or date.today()
        results_dir = self._get_results_dir(as_of_date, run_id)
        persistence = MarketMonitorPersistence(results_dir)
        persistence.ensure_layout()
        log_path = results_dir / "market_monitor.log"
        snapshot_request = MarketMonitorSnapshotRequest(
            as_of_date=request.as_of_date,
            force_refresh=request.force_refresh,
        )
        history_request = MarketMonitorHistoryRequest(
            as_of_date=request.as_of_date,
            days=request.days or 20,
            force_refresh=request.force_refresh,
        )
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
            results_dir=str(results_dir),
            log_path=str(log_path),
            llm_config=request.llm_config,
            debug_options=request.debug_options,
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
            "results_dir": str(results_dir),
            "created_at": created_at,
            "started_at": None,
            "finished_at": None,
        }
        with self._lock:
            self._runs[run_id] = run_data

        self._update_run(
            run_id,
            status=JobStatus.RUNNING,
            started_at=datetime.now(),
        )
        self._set_stage_status(run_id, persistence, "request_received", "completed")
        self._sync_manifest(run_id, persistence)
        AnalysisJobManager._append_job_log(
            log_path,
            "System",
            (
                f"Market monitor run {run_id} started: endpoint={request.trigger_endpoint}, "
                f"as_of_date={as_of_date.isoformat()}, days={request.days or 20}, "
                f"force_refresh={request.force_refresh}"
            ),
        )

        try:
            snapshot: MarketMonitorSnapshotResponse | None = None
            history: MarketMonitorHistoryResponse | None = None
            data_status: MarketMonitorDataStatusResponse | None = None
            prompt_traces: list[MarketMonitorPromptTrace] = []
            latest_fact_sheet: MarketMonitorFactSheet | None = None

            self._set_stage_status(run_id, persistence, "artifact_generation", "running")
            if request.trigger_endpoint == "snapshot":
                AnalysisJobManager._append_job_log(log_path, "System", "Building snapshot payload")
                snapshot = service.get_snapshot(snapshot_request).model_copy(update={"run_id": run_id})
                if snapshot.fact_sheet is not None:
                    persistence.write_fact_sheet_artifact(snapshot.fact_sheet)
                for trace in snapshot.prompt_traces:
                    trace_name = f"{trace.stage}_{trace.card_type or 'general'}"
                    persistence.write_prompt_trace(trace_name, trace)
                persistence.write_snapshot_artifact(snapshot)
                AnalysisJobManager._append_job_log(log_path, "System", "Snapshot payload ready")
            elif request.trigger_endpoint == "history":
                AnalysisJobManager._append_job_log(log_path, "System", "Building history payload")
                self._set_stage_status(run_id, persistence, "history_materialization", "running")
                trade_dates = service.resolve_history_trade_dates(history_request)
                history_snapshots = service.get_history_snapshots(history_request, trade_dates)
                prompt_traces: list[MarketMonitorPromptTrace] = []
                latest_fact_sheet: MarketMonitorFactSheet | None = None
                for history_snapshot in history_snapshots:
                    history_snapshot = history_snapshot.model_copy(update={"run_id": run_id})
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
                        latest_fact_sheet = history_snapshot.fact_sheet
                    for trace in history_snapshot.prompt_traces:
                        trace_name = f"history_{suffix}_{trace.card_type or trace.stage}"
                        persistence.write_prompt_trace(trace_name, trace)
                    prompt_traces.extend(history_snapshot.prompt_traces)
                    AnalysisJobManager._append_job_log(
                        log_path,
                        "System",
                        f"History replay materialized for {suffix}",
                    )
                history = service.build_history_response(
                    history_request.as_of_date or date.today(),
                    history_snapshots,
                ).model_copy(update={"run_id": run_id})
                persistence.write_history_artifact(history)
                self._set_stage_status(
                    run_id,
                    persistence,
                    "history_materialization",
                    "completed",
                )
                self._set_stage_status(run_id, persistence, "artifact_generation", "completed")
                AnalysisJobManager._append_job_log(
                    log_path,
                    "System",
                    f"History payload ready with {len(history.points)} points",
                )
            else:
                AnalysisJobManager._append_job_log(log_path, "System", "Building data status payload")
                data_status = service.get_data_status(snapshot_request).model_copy(update={"run_id": run_id})
                if data_status.fact_sheet is not None:
                    persistence.write_fact_sheet_artifact(data_status.fact_sheet)
                persistence.write_data_status_artifact(data_status)
                AnalysisJobManager._append_job_log(
                    log_path,
                    "System",
                    f"Data status payload ready with {len(data_status.open_gaps)} open gaps",
                )
                self._set_stage_status(run_id, persistence, "artifact_generation", "completed")

            fact_sheet = (
                snapshot.fact_sheet
                if snapshot is not None and snapshot.fact_sheet is not None
                else data_status.fact_sheet
                if data_status is not None and data_status.fact_sheet is not None
                else latest_fact_sheet
                if request.trigger_endpoint == "history"
                else None
            )
            prompt_traces = (
                snapshot.prompt_traces
                if snapshot is not None
                else prompt_traces
                if request.trigger_endpoint == "history"
                else []
            )
            self._update_run(
                run_id,
                status=JobStatus.COMPLETED,
                snapshot=snapshot,
                history=history,
                data_status=data_status,
                fact_sheet=fact_sheet,
                prompt_traces=prompt_traces,
                finished_at=datetime.now(),
            )
            self._sync_manifest(run_id, persistence)
            return snapshot, history, data_status
        except Exception as exc:
            if request.trigger_endpoint == "history":
                self._set_stage_status(run_id, persistence, "history_materialization", "failed", error=str(exc))
            self._set_stage_status(run_id, persistence, "artifact_generation", "failed", error=str(exc))
            AnalysisJobManager._append_job_log(
                log_path,
                "Error",
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}",
            )
            self._update_run(
                run_id,
                status=JobStatus.FAILED,
                error_message=str(exc),
                finished_at=datetime.now(),
            )
            self._sync_manifest(run_id, persistence, recoverable=True)
            raise

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
            debug_options=snapshot["request"].debug_options,
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
            else snapshot["request"].as_of_date or snapshot["created_at"].date()
        )
        return HistoricalMarketMonitorRunSummary(
            run_id=snapshot["run_id"],
            trigger_endpoint=snapshot["request"].trigger_endpoint,
            as_of_date=as_of_date,
            days=snapshot["request"].days,
            status=snapshot["status"],
            generated_at=snapshot.get("finished_at") or snapshot.get("started_at") or snapshot["created_at"],
            data_freshness=response.data_freshness if response is not None else None,
            source_completeness=(data_status.source_coverage.completeness if data_status is not None else response.source_coverage.completeness if response is not None else None),
            regime_label=response.execution_card.regime_label if response is not None else None,
            degraded=(data_status.source_coverage.degraded if data_status is not None else response.source_coverage.degraded if response is not None else False),
            recoverable=manifest.recoverable if manifest is not None else False,
            error_message=snapshot.get("error_message"),
            log_path=snapshot.get("log_path"),
            results_dir=snapshot.get("results_dir"),
        )

    def _get_results_dir(self, as_of_date: date, run_id: str) -> Path:
        return self.runs_root / as_of_date.isoformat() / run_id
