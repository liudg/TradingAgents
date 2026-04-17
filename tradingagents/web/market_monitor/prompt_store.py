from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .cache import MARKET_MONITOR_CACHE_DIR
from .errors import MarketMonitorCorruptedStateError, MarketMonitorNotFoundError
from .io_utils import load_json, write_json_atomic
from .run_store import MonitorRunStore
from .schemas import MarketMonitorPromptDetail, MarketMonitorPromptSummary


class PromptCaptureStore:
    def __init__(self, root: Path | None = None, run_store: MonitorRunStore | None = None) -> None:
        self.run_store = run_store
        if run_store is not None:
            self.root = run_store.root
        else:
            self.root = root or (MARKET_MONITOR_CACHE_DIR / "runs")
        self.root.mkdir(parents=True, exist_ok=True)

    def capture_prompt(
        self,
        run_id: str,
        stage_key: str,
        attempt: int,
        model: str,
        payload: dict[str, Any],
    ) -> MarketMonitorPromptDetail:
        created_at = datetime.now(timezone.utc)
        prompt_id = f"{stage_key}-attempt-{attempt}"
        prompt_dir = self._prompt_dir(run_id, stage_key)
        prompt_dir.mkdir(parents=True, exist_ok=True)
        path = prompt_dir / f"attempt-{attempt}.json"
        record = {
            "prompt_id": prompt_id,
            "run_id": run_id,
            "stage_key": stage_key,
            "attempt": attempt,
            "created_at": created_at.isoformat(),
            "model": model,
            "payload": payload,
            "file_path": str(path),
            "request_status": "captured",
            "request_error": None,
            "status_updated_at": created_at.isoformat(),
        }
        write_json_atomic(path, record)
        return MarketMonitorPromptDetail.model_validate(record)

    def mark_prompt_status(
        self,
        run_id: str,
        prompt_id: str,
        *,
        request_status: str,
        request_error: str | None = None,
    ) -> MarketMonitorPromptDetail:
        detail = self.get_prompt(run_id, prompt_id)
        updated = detail.model_copy(
            update={
                "request_status": request_status,
                "request_error": request_error,
                "status_updated_at": datetime.now(timezone.utc),
            }
        )
        path = self._prompt_dir(run_id, updated.stage_key) / f"attempt-{updated.attempt}.json"
        write_json_atomic(path, updated.model_dump(mode="json"))
        return updated

    def list_prompts(self, run_id: str) -> list[MarketMonitorPromptSummary]:
        prompt_dir = self._run_prompt_root(run_id)
        if not prompt_dir.exists():
            return []
        items: list[MarketMonitorPromptSummary] = []
        for path in sorted(prompt_dir.glob("*/*.json")):
            try:
                payload = load_json(path, raise_on_error=True)
            except Exception as exc:
                raise MarketMonitorCorruptedStateError(f"提示词列表存在损坏文件 {path.name}: {exc}") from exc
            if payload is None:
                continue
            try:
                items.append(MarketMonitorPromptSummary.model_validate(payload))
            except ValidationError as exc:
                raise MarketMonitorCorruptedStateError(f"提示词列表存在结构无效文件 {path.name}: {exc}") from exc
        items.sort(key=lambda item: item.created_at)
        return items

    def get_prompt(self, run_id: str, prompt_id: str) -> MarketMonitorPromptDetail:
        stage_key, attempt = _parse_prompt_id(prompt_id)
        path = self._prompt_dir(run_id, stage_key) / f"attempt-{attempt}.json"
        try:
            payload = load_json(path, raise_on_error=True)
        except Exception as exc:
            raise MarketMonitorCorruptedStateError(f"{prompt_id} 提示词记录损坏: {exc}") from exc
        if payload is None:
            raise MarketMonitorNotFoundError(prompt_id)
        try:
            return MarketMonitorPromptDetail.model_validate(payload)
        except ValidationError as exc:
            raise MarketMonitorCorruptedStateError(f"{prompt_id} 提示词记录结构无效: {exc}") from exc

    def _run_prompt_root(self, run_id: str) -> Path:
        if self.run_store is not None:
            return self.run_store.resolve_run_dir(run_id) / "prompts"
        return self.root / run_id / "prompts"

    def _prompt_dir(self, run_id: str, stage_key: str) -> Path:
        return self._run_prompt_root(run_id) / stage_key


def _parse_prompt_id(prompt_id: str) -> tuple[str, int]:
    stage_key, separator, attempt_text = prompt_id.rpartition("-attempt-")
    if not separator or not attempt_text.isdigit():
        raise MarketMonitorNotFoundError(prompt_id)
    return stage_key, int(attempt_text)
