from __future__ import annotations

import json
import traceback
from datetime import date, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.web.analysis.manager import AnalysisJobManager
from tradingagents.web.market_monitor.io_utils import write_json_atomic
from tradingagents.web.market_monitor.schemas import (
    HistoricalMarketMonitorRunDetail,
    HistoricalMarketMonitorRunSummary,
    MarketMonitorDataStatusResponse,
    MarketMonitorHistoryRequest,
    MarketMonitorHistoryResponse,
    MarketMonitorRunRequest,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
)
from tradingagents.web.market_monitor.snapshot_service import MarketMonitorSnapshotService
from tradingagents.web.schemas import AnalysisJobLogEntry, JobStatus


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
        )
        snapshot, _, _ = self._execute_run(run_request)
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
        )
        _, history, _ = self._execute_run(run_request)
        return history

    def run_data_status(
        self,
        request: MarketMonitorSnapshotRequest,
    ) -> MarketMonitorDataStatusResponse:
        run_request = MarketMonitorRunRequest(
            trigger_endpoint="data_status",
            as_of_date=request.as_of_date,
            force_refresh=request.force_refresh,
        )
        _, _, data_status = self._execute_run(run_request)
        return data_status

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

    def _execute_run(
        self,
        request: MarketMonitorRunRequest,
    ) -> tuple[MarketMonitorSnapshotResponse, MarketMonitorHistoryResponse, MarketMonitorDataStatusResponse]:
        run_id = uuid4().hex
        as_of_date = request.as_of_date or date.today()
        results_dir = self._get_results_dir(as_of_date, run_id)
        results_dir.mkdir(parents=True, exist_ok=True)
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
        run_data = {
            "run_id": run_id,
            "request": request,
            "status": JobStatus.PENDING,
            "snapshot": None,
            "history": None,
            "data_status": None,
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
            AnalysisJobManager._append_job_log(log_path, "System", "Building snapshot payload")
            snapshot = self.service.get_snapshot(snapshot_request).model_copy(update={"run_id": run_id})
            AnalysisJobManager._append_job_log(log_path, "System", "Snapshot payload ready")

            AnalysisJobManager._append_job_log(log_path, "System", "Building history payload")
            history = self.service.get_history(history_request).model_copy(update={"run_id": run_id})
            AnalysisJobManager._append_job_log(
                log_path,
                "System",
                f"History payload ready with {len(history.points)} points",
            )

            AnalysisJobManager._append_job_log(log_path, "System", "Building data status payload")
            data_status = self.service.get_data_status(snapshot_request).model_copy(update={"run_id": run_id})
            AnalysisJobManager._append_job_log(
                log_path,
                "System",
                f"Data status payload ready with {len(data_status.open_gaps)} open gaps",
            )

            self._update_run(
                run_id,
                status=JobStatus.COMPLETED,
                snapshot=snapshot,
                history=history,
                data_status=data_status,
                finished_at=datetime.now(),
            )
            self._persist_run_snapshot(run_id)
            return snapshot, history, data_status
        except Exception as exc:
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
            self._persist_run_snapshot(run_id)
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
        for snapshot_path in self.runs_root.rglob("market_monitor_snapshot.json"):
            try:
                payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
                run_request = MarketMonitorRunRequest.model_validate(payload["request"])
                snapshot = (
                    MarketMonitorSnapshotResponse.model_validate(payload["snapshot"])
                    if payload.get("snapshot")
                    else None
                )
                history = (
                    MarketMonitorHistoryResponse.model_validate(payload["history"])
                    if payload.get("history")
                    else None
                )
                data_status = (
                    MarketMonitorDataStatusResponse.model_validate(payload["data_status"])
                    if payload.get("data_status")
                    else None
                )
                run_data = {
                    "run_id": payload["run_id"],
                    "request": run_request,
                    "status": JobStatus(payload["status"]),
                    "snapshot": snapshot,
                    "history": history,
                    "data_status": data_status,
                    "error_message": payload.get("error_message"),
                    "log_path": payload.get("log_path") or str(snapshot_path.parent / "market_monitor.log"),
                    "results_dir": payload.get("results_dir") or str(snapshot_path.parent),
                    "created_at": datetime.fromisoformat(payload["created_at"]),
                    "started_at": AnalysisJobManager._parse_optional_datetime(payload.get("started_at")),
                    "finished_at": AnalysisJobManager._parse_optional_datetime(payload.get("finished_at")),
                }
            except Exception:
                continue
            self._runs[run_data["run_id"]] = run_data

    def _persist_run_snapshot(self, run_id: str) -> None:
        with self._lock:
            run_data = self._runs.get(run_id)
            if not run_data:
                return
            snapshot = dict(run_data)
        snapshot_dir = Path(snapshot["results_dir"])
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": snapshot["run_id"],
            "status": snapshot["status"].value,
            "request": snapshot["request"].model_dump(mode="json"),
            "snapshot": snapshot["snapshot"].model_dump(mode="json") if snapshot.get("snapshot") else None,
            "history": snapshot["history"].model_dump(mode="json") if snapshot.get("history") else None,
            "data_status": snapshot["data_status"].model_dump(mode="json") if snapshot.get("data_status") else None,
            "error_message": snapshot.get("error_message"),
            "log_path": snapshot.get("log_path"),
            "results_dir": snapshot.get("results_dir"),
            "created_at": snapshot["created_at"].isoformat(),
            "started_at": AnalysisJobManager._format_optional_datetime(snapshot.get("started_at")),
            "finished_at": AnalysisJobManager._format_optional_datetime(snapshot.get("finished_at")),
        }
        write_json_atomic(snapshot_dir / "market_monitor_snapshot.json", payload)

    def _build_summary(self, snapshot: dict[str, Any]) -> HistoricalMarketMonitorRunSummary:
        response: MarketMonitorSnapshotResponse | None = snapshot.get("snapshot")
        data_status: MarketMonitorDataStatusResponse | None = snapshot.get("data_status")
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
            error_message=snapshot.get("error_message"),
            log_path=snapshot.get("log_path"),
            results_dir=snapshot.get("results_dir"),
        )

    def _get_results_dir(self, as_of_date: date, run_id: str) -> Path:
        return self.runs_root / as_of_date.isoformat() / run_id
