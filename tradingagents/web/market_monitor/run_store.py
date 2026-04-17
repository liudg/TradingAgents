from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from shutil import rmtree
from uuid import uuid4

from tradingagents.default_config import DEFAULT_CONFIG

from .cache import MARKET_MONITOR_CACHE_DIR
from .errors import MarketMonitorCorruptedStateError, MarketMonitorNotFoundError
from .io_utils import load_json, write_json_atomic
from .schemas import (
    MarketMonitorRunDetail,
    MarketMonitorRunEvidenceResponse,
    MarketMonitorRunLogEntry,
    MarketMonitorRunStageDetail,
    MarketMonitorRunStagesResponse,
)

LOG_PATTERN = re.compile(r"^(?P<timestamp>[^ ]+) \[(?P<level>[^\]]+)\] (?P<content>.*)$")
_SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RUN_INDEX_FILE = "run_index.json"


def _validate_id(value: str) -> str:
    if not _SAFE_ID_PATTERN.match(value):
        raise MarketMonitorNotFoundError(value)
    return value


class MonitorRunStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (MARKET_MONITOR_CACHE_DIR / "runs")
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / _RUN_INDEX_FILE

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
        path = run_dir / "run.json"
        write_json_atomic(path, detail.model_dump(mode="json"))
        self._register_run_dir(detail.run_id, run_dir)

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

    def list_runs(self) -> list[MarketMonitorRunDetail]:
        runs: list[MarketMonitorRunDetail] = []
        for path in self.root.glob("*/*/run.json"):
            payload = load_json(path)
            if payload is None:
                continue
            try:
                runs.append(MarketMonitorRunDetail.model_validate(payload))
            except Exception:
                continue
        runs.sort(key=lambda item: item.created_at, reverse=True)
        return runs

    def save_stages(self, run_id: str, stages: list[MarketMonitorRunStageDetail]) -> None:
        payload = MarketMonitorRunStagesResponse(run_id=run_id, stages=stages)
        write_json_atomic(self.resolve_run_dir(run_id) / "stages.json", payload.model_dump(mode="json"))

    def get_stages(self, run_id: str) -> MarketMonitorRunStagesResponse:
        path = self.resolve_run_dir(run_id) / "stages.json"
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
        write_json_atomic(self.resolve_run_dir(run_id) / "evidence.json", evidence.model_dump(mode="json"))

    def get_evidence(self, run_id: str) -> MarketMonitorRunEvidenceResponse:
        path = self.resolve_run_dir(run_id) / "evidence.json"
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

    def append_log(self, run_id: str, level: str, content: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        path = self.resolve_run_dir(run_id) / "events.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{now} [{level}] {content}\n")

    def list_logs(self, run_id: str) -> list[MarketMonitorRunLogEntry]:
        path = self.resolve_run_dir(run_id) / "events.log"
        if not path.exists():
            return []
        entries: list[MarketMonitorRunLogEntry] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = LOG_PATTERN.match(line)
            if not match:
                entries.append(MarketMonitorRunLogEntry(line_no=index, timestamp=None, level="Raw", content=line))
                continue
            entries.append(
                MarketMonitorRunLogEntry(
                    line_no=index,
                    timestamp=datetime.fromisoformat(match.group("timestamp")),
                    level=match.group("level"),
                    content=match.group("content"),
                )
            )
        return entries

    def _run_dir(self, run_id: str, as_of_date: date) -> Path:
        _validate_id(run_id)
        path = self.root / as_of_date.isoformat() / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_run_dir(self, run_id: str) -> Path:
        _validate_id(run_id)
        indexed_path = self._resolve_indexed_run_dir(run_id)
        if indexed_path is not None:
            return indexed_path
        recovered_path = self._recover_run_dir(run_id)
        if recovered_path is not None:
            self._register_run_dir(run_id, recovered_path)
            return recovered_path
        raise MarketMonitorNotFoundError(run_id)

    def cleanup_runs(self, retention_days: int, now: datetime | None = None) -> int:
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
            rmtree(day_dir, ignore_errors=True)
            removed += 1
        if removed:
            self._prune_run_index()
        return removed

    def _load_run_index(self) -> dict[str, str]:
        payload = load_json(self._index_path) or {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items()}

    def _save_run_index(self, index: dict[str, str]) -> None:
        write_json_atomic(self._index_path, index)

    def _register_run_dir(self, run_id: str, run_dir: Path) -> None:
        index = self._load_run_index()
        relative_path = run_dir.relative_to(self.root).as_posix()
        if index.get(run_id) == relative_path:
            return
        index[run_id] = relative_path
        self._save_run_index(index)

    def _resolve_indexed_run_dir(self, run_id: str) -> Path | None:
        index = self._load_run_index()
        relative_path = index.get(run_id)
        if not relative_path:
            return None
        path = self.root / Path(relative_path)
        if path.is_dir():
            return path
        index.pop(run_id, None)
        self._save_run_index(index)
        return None

    def _recover_run_dir(self, run_id: str) -> Path | None:
        for day_dir in self.root.iterdir():
            if not day_dir.is_dir() or not _DATE_PATTERN.match(day_dir.name):
                continue
            candidate = day_dir / run_id
            if candidate.is_dir():
                return candidate
        return None

    def _prune_run_index(self) -> None:
        index = self._load_run_index()
        next_index = {
            run_id: relative_path
            for run_id, relative_path in index.items()
            if (self.root / Path(relative_path)).is_dir()
        }
        if next_index == index:
            return
        self._save_run_index(next_index)
