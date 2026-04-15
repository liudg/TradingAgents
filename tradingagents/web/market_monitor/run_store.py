from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .cache import MARKET_MONITOR_CACHE_DIR
from .errors import MarketMonitorNotFoundError
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
        path = self._run_dir(detail.run_id, as_of_date=detail.as_of_date) / "run.json"
        write_json_atomic(path, detail.model_dump(mode="json"))

    def get_run(self, run_id: str) -> MarketMonitorRunDetail:
        payload = load_json(self.resolve_run_dir(run_id) / "run.json")
        if payload is None:
            raise MarketMonitorNotFoundError(run_id)
        return MarketMonitorRunDetail.model_validate(payload)

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
        write_json_atomic((self._run_dir(run_id) / "stages.json"), payload.model_dump(mode="json"))

    def get_stages(self, run_id: str) -> MarketMonitorRunStagesResponse:
        payload = load_json(self.resolve_run_dir(run_id) / "stages.json")
        if payload is None:
            raise MarketMonitorNotFoundError(run_id)
        return MarketMonitorRunStagesResponse.model_validate(payload)

    def save_evidence(self, run_id: str, evidence: MarketMonitorRunEvidenceResponse) -> None:
        write_json_atomic((self._run_dir(run_id) / "evidence.json"), evidence.model_dump(mode="json"))

    def get_evidence(self, run_id: str) -> MarketMonitorRunEvidenceResponse:
        payload = load_json(self.resolve_run_dir(run_id) / "evidence.json")
        if payload is None:
            raise MarketMonitorNotFoundError(run_id)
        return MarketMonitorRunEvidenceResponse.model_validate(payload)

    def append_log(self, run_id: str, level: str, content: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        path = self._run_dir(run_id) / "events.log"
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

    def _run_dir(self, run_id: str, as_of_date: date | None = None) -> Path:
        return self.resolve_run_dir(run_id, as_of_date=as_of_date, create=True)

    def resolve_run_dir(self, run_id: str, as_of_date: date | None = None, create: bool = False) -> Path:
        _validate_id(run_id)
        if as_of_date is not None:
            path = self.root / as_of_date.isoformat() / run_id
            if create:
                path.mkdir(parents=True, exist_ok=True)
            return path

        matches = [path for path in self.root.glob(f"*/{run_id}") if path.is_dir()]
        if len(matches) == 1:
            return matches[0]
        if not matches and create:
            path = self.root / run_id
            path.mkdir(parents=True, exist_ok=True)
            return path
        raise MarketMonitorNotFoundError(run_id)
