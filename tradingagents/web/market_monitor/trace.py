from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .cache import MARKET_MONITOR_CACHE_DIR
from .errors import MarketMonitorError, MarketMonitorNotFoundError
from .io_utils import load_json, write_json_atomic
from .schemas import (
    MarketMonitorTraceDetail,
    MarketMonitorTraceLogEntry,
    MarketMonitorTraceSummary,
)


TRACE_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \[(?P<level>[^\]]+)\] (?P<content>.*)$"
)


class MarketMonitorTraceLogger:
    def __init__(self, trace_root: Path, as_of_date: date, force_refresh: bool) -> None:
        self.trace_id = uuid4().hex
        self.as_of_date = as_of_date
        self.started_at = datetime.now(timezone.utc)
        self.finished_at: datetime | None = None
        self.trace_dir = trace_root / as_of_date.isoformat() / self.trace_id
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.trace_dir / "events.log"
        self.snapshot_path = self.trace_dir / "trace_snapshot.json"
        self.payload: dict[str, Any] = {
            "trace_id": self.trace_id,
            "as_of_date": as_of_date.isoformat(),
            "status": "running",
            "force_refresh": force_refresh,
            "started_at": self.started_at.isoformat(),
            "finished_at": None,
            "duration_ms": None,
            "overall_confidence": None,
            "long_term_label": None,
            "execution_label": None,
            "log_path": str(self.log_path),
            "snapshot_path": str(self.snapshot_path),
            "request": {},
            "cache_decision": {},
            "dataset_summary": {},
            "context_summary": {},
            "assessment_summary": {},
            "response_summary": {},
            "error": {},
        }
        self._persist_running_snapshot()

    def log_event(self, level: str, content: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        normalized = content.replace("\r\n", "\n").replace("\n", " ")
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} [{level}] {normalized}\n")
        self._persist_running_snapshot()

    def set_stage(self, stage_name: str, payload: dict[str, Any]) -> None:
        self.payload[stage_name] = payload
        self._persist_running_snapshot()

    def set_summary_fields(self, **fields: Any) -> None:
        self.payload.update(fields)
        self._persist_running_snapshot()

    def complete(self, response_summary: dict[str, Any]) -> None:
        self.payload["status"] = "completed"
        self.payload["response_summary"] = response_summary
        self._persist()

    def fail(self, stage: str, exc: Exception) -> None:
        self.payload["status"] = "failed"
        self.payload["error"] = {
            "stage": stage,
            "type": exc.__class__.__name__,
            "message": str(exc),
        }
        self._persist()

    def _persist(self) -> None:
        self.finished_at = datetime.now(timezone.utc)
        self.payload["finished_at"] = self.finished_at.isoformat()
        self.payload["duration_ms"] = int(
            (self.finished_at - self.started_at).total_seconds() * 1000
        )
        write_json_atomic(self.snapshot_path, self.payload)

    def _persist_running_snapshot(self) -> None:
        payload = dict(self.payload)
        payload["finished_at"] = None
        payload["duration_ms"] = None
        write_json_atomic(self.snapshot_path, payload)


class MarketMonitorTraceStore:
    def __init__(self, trace_root: Path | None = None) -> None:
        self.trace_root = trace_root or (MARKET_MONITOR_CACHE_DIR / "traces")
        self.trace_root.mkdir(parents=True, exist_ok=True)

    def create_logger(self, as_of_date: date, force_refresh: bool) -> MarketMonitorTraceLogger:
        return MarketMonitorTraceLogger(self.trace_root, as_of_date, force_refresh)

    def list_traces(
        self,
        as_of_date: date | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[MarketMonitorTraceSummary]:
        summaries: list[MarketMonitorTraceSummary] = []
        for snapshot_path in self._iter_snapshot_paths(as_of_date):
            payload = load_json(snapshot_path)
            if payload is None:
                continue
            if status and payload.get("status") != status:
                continue
            try:
                summaries.append(MarketMonitorTraceSummary.model_validate(payload))
            except Exception:
                continue
        summaries.sort(key=lambda item: item.started_at, reverse=True)
        return summaries[:limit] if limit > 0 else []

    def get_trace_detail(self, trace_id: str) -> MarketMonitorTraceDetail:
        payload = self._get_trace_payload(trace_id)
        return MarketMonitorTraceDetail.model_validate(_sanitize_trace_payload(payload))

    def list_trace_logs(self, trace_id: str) -> list[MarketMonitorTraceLogEntry]:
        payload = self._get_trace_payload(trace_id)
        log_path = Path(str(payload.get("log_path") or ""))
        if not log_path.exists():
            raise MarketMonitorNotFoundError(f"Trace log file not found for {trace_id}")
        entries: list[MarketMonitorTraceLogEntry] = []
        for index, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
            entries.append(_parse_trace_log_line(index, line))
        return entries

    def _get_trace_payload(self, trace_id: str) -> dict[str, Any]:
        snapshot_path = self._find_snapshot_path(trace_id)
        if snapshot_path is None:
            raise MarketMonitorNotFoundError(trace_id)
        payload = load_json(snapshot_path)
        if payload is None:
            raise MarketMonitorError(f"Trace snapshot is unreadable for {trace_id}")
        return payload

    def _iter_snapshot_paths(self, as_of_date: date | None) -> list[Path]:
        if as_of_date is not None:
            base_dir = self.trace_root / as_of_date.isoformat()
            if not base_dir.exists():
                return []
            return sorted(base_dir.rglob("trace_snapshot.json"), reverse=True)
        return sorted(self.trace_root.rglob("trace_snapshot.json"), reverse=True)

    def _find_snapshot_path(self, trace_id: str) -> Path | None:
        for snapshot_path in self.trace_root.rglob("trace_snapshot.json"):
            if snapshot_path.parent.name == trace_id:
                return snapshot_path
        return None


def _parse_trace_log_line(line_no: int, raw_line: str) -> MarketMonitorTraceLogEntry:
    matched = TRACE_LOG_PATTERN.match(raw_line)
    if not matched:
        return MarketMonitorTraceLogEntry(
            line_no=line_no,
            timestamp=None,
            level="Raw",
            content=raw_line,
        )

    return MarketMonitorTraceLogEntry(
        line_no=line_no,
        timestamp=datetime.strptime(matched.group("timestamp"), "%Y-%m-%d %H:%M:%S"),
        level=matched.group("level"),
        content=matched.group("content"),
    )


def _sanitize_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(payload)
    sanitized.pop("log_path", None)
    sanitized.pop("snapshot_path", None)
    return sanitized
