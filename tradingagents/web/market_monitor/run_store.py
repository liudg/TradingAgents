from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from .cache import MARKET_MONITOR_CACHE_DIR
from .errors import MarketMonitorConflictError, MarketMonitorCorruptedStateError, MarketMonitorNotFoundError
from .io_utils import load_json, write_json_atomic
from .schemas import (
    CleanupRunStatus,
    MarketMonitorRunCleanupRequest,
    MarketMonitorRunDetail,
    MarketMonitorRunEvidenceResponse,
    MarketMonitorRunLogEntry,
    MarketMonitorRunStageDetail,
    MarketMonitorRunStagesResponse,
    MarketMonitorRunSummary,
)

_SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ARTIFACTS_DIR = "artifacts"
_EVENTS_FILE = "events.jsonl"


def _validate_id(value: str) -> str:
    if not _SAFE_ID_PATTERN.match(value):
        raise MarketMonitorNotFoundError(value)
    return value


class MonitorRunStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (MARKET_MONITOR_CACHE_DIR / "runs")
        self.root.mkdir(parents=True, exist_ok=True)

    def create_run(self, as_of_date: date) -> MarketMonitorRunDetail:
        run_id = uuid4().hex
        now = datetime.now(timezone.utc)
        detail = MarketMonitorRunDetail(
            run_id=run_id,
            as_of_date=as_of_date,
            status="running",
            current_stage="pending",
            created_at=now,
            started_at=now,
            finished_at=None,
            error_message=None,
            result=None,
        )
        self.save_run(detail)
        self.save_stages(
            run_id,
            [
                MarketMonitorRunStageDetail(stage_key="input_bundle", label="本地输入摘要", status="pending"),
                MarketMonitorRunStageDetail(stage_key="search_slots", label="搜索补数", status="pending"),
                MarketMonitorRunStageDetail(stage_key="fact_sheet", label="事实整编", status="pending"),
                MarketMonitorRunStageDetail(stage_key="judgment_group_a", label="环境与系统风险裁决", status="pending"),
                MarketMonitorRunStageDetail(stage_key="judgment_group_b", label="短线与事件裁决", status="pending"),
                MarketMonitorRunStageDetail(stage_key="execution_decision", label="执行建议", status="pending"),
            ],
        )
        self.save_evidence(
            run_id,
            MarketMonitorRunEvidenceResponse(run_id=run_id, evidence_index={}, search_slots={}, open_gaps=[]),
        )
        return detail

    def save_run(self, detail: MarketMonitorRunDetail) -> None:
        run_dir = self._run_dir(detail.run_id, as_of_date=detail.as_of_date)
        write_json_atomic(run_dir / "run.json", detail.model_dump(mode="json"))

    def get_run(self, run_id: str) -> MarketMonitorRunDetail:
        path = self.resolve_run_dir(run_id) / "run.json"
        try:
            payload = load_json(path, raise_on_error=True)
        except Exception as exc:
            raise MarketMonitorCorruptedStateError(f"{run_id} 的运行元数据损坏: {exc}") from exc
        if payload is None:
            raise MarketMonitorNotFoundError(run_id)
        try:
            return MarketMonitorRunDetail.model_validate(payload)
        except Exception as exc:
            raise MarketMonitorCorruptedStateError(f"{run_id} 的运行元数据结构无效: {exc}") from exc

    def list_runs(self, statuses: list[CleanupRunStatus] | None = None, limit: int | None = None) -> list[MarketMonitorRunSummary]:
        runs: list[MarketMonitorRunSummary] = []
        allowed_statuses = set(statuses or [])
        for path in self.root.glob("*/*/run.json"):
            payload = load_json(path)
            if payload is None:
                continue
            try:
                detail = MarketMonitorRunDetail.model_validate(payload)
            except Exception:
                continue
            if allowed_statuses and detail.status not in allowed_statuses:
                continue
            runs.append(
                MarketMonitorRunSummary(
                    run_id=detail.run_id,
                    as_of_date=detail.as_of_date,
                    status=detail.status,
                    current_stage=detail.current_stage,
                    created_at=detail.created_at,
                    started_at=detail.started_at,
                    finished_at=detail.finished_at,
                    error_message=detail.error_message,
                )
            )
        runs.sort(key=lambda item: item.created_at, reverse=True)
        return runs[:limit] if limit is not None else runs

    def save_stages(self, run_id: str, stages: list[MarketMonitorRunStageDetail]) -> None:
        payload = MarketMonitorRunStagesResponse(run_id=run_id, stages=stages)
        write_json_atomic(self._artifact_path(run_id, "stages.json"), payload.model_dump(mode="json"))

    def get_stages(self, run_id: str) -> MarketMonitorRunStagesResponse:
        path = self._artifact_path(run_id, "stages.json")
        try:
            payload = load_json(path, raise_on_error=True)
        except Exception as exc:
            raise MarketMonitorCorruptedStateError(f"{run_id} 的阶段元数据损坏: {exc}") from exc
        if payload is None:
            raise MarketMonitorNotFoundError(run_id)
        try:
            return MarketMonitorRunStagesResponse.model_validate(payload)
        except Exception as exc:
            raise MarketMonitorCorruptedStateError(f"{run_id} 的阶段元数据结构无效: {exc}") from exc

    def save_evidence(self, run_id: str, evidence: MarketMonitorRunEvidenceResponse) -> None:
        write_json_atomic(self._artifact_path(run_id, "evidence.json"), evidence.model_dump(mode="json"))

    def get_evidence(self, run_id: str) -> MarketMonitorRunEvidenceResponse:
        path = self._artifact_path(run_id, "evidence.json")
        try:
            payload = load_json(path, raise_on_error=True)
        except Exception as exc:
            raise MarketMonitorCorruptedStateError(f"{run_id} 的证据元数据损坏: {exc}") from exc
        if payload is None:
            raise MarketMonitorNotFoundError(run_id)
        try:
            return MarketMonitorRunEvidenceResponse.model_validate(payload)
        except Exception as exc:
            raise MarketMonitorCorruptedStateError(f"{run_id} 的证据元数据结构无效: {exc}") from exc

    def append_event(
        self,
        run_id: str,
        level: str,
        event_type: str,
        message: str,
        *,
        stage_key: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        path = self._artifact_path(run_id, _EVENTS_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event_type": event_type,
            "stage_key": stage_key,
            "message": message,
            "details": details or {},
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str))
            handle.write("\n")

    def list_logs(self, run_id: str) -> list[MarketMonitorRunLogEntry]:
        path = self._artifact_path(run_id, _EVENTS_FILE)
        if not path.exists():
            return []
        return self._read_jsonl_logs(path)

    def delete_run(self, run_id: str) -> None:
        run = self.get_run(run_id)
        if run.status == "running":
            raise MarketMonitorConflictError("运行中的任务不能删除")
        rmtree(self.resolve_run_dir(run_id), ignore_errors=True)

    def cleanup_runs(self, request: MarketMonitorRunCleanupRequest, now: datetime | None = None) -> list[str]:
        reference = now or datetime.now(timezone.utc)
        statuses = set(request.statuses or [])
        if request.delete_all_failed:
            statuses.add("failed")
        removed: list[str] = []
        for run in self.list_runs():
            if run.status == "running":
                continue
            if statuses and run.status not in statuses:
                continue
            if request.older_than_days is not None:
                age_days = (reference.date() - run.as_of_date).days
                if age_days < request.older_than_days:
                    continue
            self.delete_run(run.run_id)
            removed.append(run.run_id)
            if request.limit is not None and len(removed) >= request.limit:
                break
        return removed

    def cleanup_runs_by_retention(self, retention_days: int, now: datetime | None = None) -> int:
        if retention_days <= 0:
            return 0
        reference = now or datetime.now(timezone.utc)
        removed = 0
        for day_dir in self.root.iterdir():
            if not day_dir.is_dir() or not _DATE_PATTERN.match(day_dir.name):
                continue
            try:
                run_date = date.fromisoformat(day_dir.name)
            except ValueError:
                continue
            age_days = (reference.date() - run_date).days
            if age_days <= retention_days:
                continue
            for run_dir in day_dir.iterdir():
                if not run_dir.is_dir():
                    continue
                payload = load_json(run_dir / "run.json") or {}
                if payload.get("status") == "running":
                    continue
                rmtree(run_dir, ignore_errors=True)
                removed += 1
            if not any(day_dir.iterdir()):
                rmtree(day_dir, ignore_errors=True)
        return removed

    def _read_jsonl_logs(self, path: Path) -> list[MarketMonitorRunLogEntry]:
        entries: list[MarketMonitorRunLogEntry] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                entries.append(
                    MarketMonitorRunLogEntry(
                        line_no=index,
                        timestamp=None,
                        level="Raw",
                        event_type=None,
                        stage_key=None,
                        content=line,
                        details={},
                    )
                )
                continue
            if not isinstance(payload, dict):
                entries.append(
                    MarketMonitorRunLogEntry(
                        line_no=index,
                        timestamp=None,
                        level="Raw",
                        event_type=None,
                        stage_key=None,
                        content=line,
                        details={},
                    )
                )
                continue
            timestamp = None
            raw_timestamp = payload.get("timestamp")
            if isinstance(raw_timestamp, str):
                try:
                    timestamp = datetime.fromisoformat(raw_timestamp)
                except ValueError:
                    timestamp = None
            message = payload.get("message")
            if not isinstance(message, str) or not message:
                message = str(payload.get("content") or line)
            level = payload.get("level")
            if not isinstance(level, str) or not level:
                level = "Info"
            event_type = payload.get("event_type")
            if not isinstance(event_type, str) or not event_type:
                event_type = None
            stage_key = payload.get("stage_key")
            if not isinstance(stage_key, str) or not stage_key:
                stage_key = None
            details = payload.get("details")
            if not isinstance(details, dict):
                details = {}
            entries.append(
                MarketMonitorRunLogEntry(
                    line_no=index,
                    timestamp=timestamp,
                    level=level,
                    event_type=event_type,
                    stage_key=stage_key,
                    content=message,
                    details=details,
                )
            )
        return entries

    def _run_dir(self, run_id: str, as_of_date: date) -> Path:
        _validate_id(run_id)
        path = self.root / as_of_date.isoformat() / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _artifacts_dir(self, run_id: str) -> Path:
        path = self.resolve_run_dir(run_id) / _ARTIFACTS_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _artifact_path(self, run_id: str, filename: str) -> Path:
        return self._artifacts_dir(run_id) / filename

    def resolve_run_dir(self, run_id: str) -> Path:
        _validate_id(run_id)
        for day_dir in self.root.iterdir():
            if not day_dir.is_dir() or not _DATE_PATTERN.match(day_dir.name):
                continue
            candidate = day_dir / run_id
            if candidate.is_dir():
                return candidate
        raise MarketMonitorNotFoundError(run_id)
