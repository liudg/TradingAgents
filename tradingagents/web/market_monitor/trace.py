from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from uuid import uuid4

from .cache import MARKET_MONITOR_CACHE_DIR
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
        self.started_at = datetime.now()
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
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
        self.finished_at = datetime.now()
        self.payload["finished_at"] = self.finished_at.isoformat()
        self.payload["duration_ms"] = int(
            (self.finished_at - self.started_at).total_seconds() * 1000
        )
        _write_json_atomic(self.snapshot_path, self.payload)

    def _persist_running_snapshot(self) -> None:
        payload = dict(self.payload)
        payload["finished_at"] = None
        payload["duration_ms"] = None
        _write_json_atomic(self.snapshot_path, payload)


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
            payload = _load_json(snapshot_path)
            if payload is None:
                continue
            if status and payload.get("status") != status:
                continue
            try:
                summaries.append(MarketMonitorTraceSummary.model_validate(payload))
            except Exception:
                continue
        summaries.sort(key=lambda item: item.started_at, reverse=True)
        return summaries[: max(limit, 1)]

    def get_trace_detail(self, trace_id: str) -> MarketMonitorTraceDetail:
        payload = self._get_trace_payload(trace_id)
        return MarketMonitorTraceDetail.model_validate(_sanitize_trace_payload(payload))

    def list_trace_logs(self, trace_id: str) -> list[MarketMonitorTraceLogEntry]:
        payload = self._get_trace_payload(trace_id)
        log_path = Path(str(payload.get("log_path") or ""))
        if not log_path.exists():
            raise ValueError(f"Trace log file not found for {trace_id}")
        entries: list[MarketMonitorTraceLogEntry] = []
        for index, line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
            entries.append(_parse_trace_log_line(index, line))
        return entries

    def _get_trace_payload(self, trace_id: str) -> dict[str, Any]:
        snapshot_path = self._find_snapshot_path(trace_id)
        if snapshot_path is None:
            raise KeyError(trace_id)
        payload = _load_json(snapshot_path)
        if payload is None:
            raise ValueError(f"Trace snapshot is unreadable for {trace_id}")
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


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as handle:
        temp_path = Path(handle.name)
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
    try:
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


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
