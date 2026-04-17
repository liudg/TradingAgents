from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cache import MARKET_MONITOR_CACHE_DIR
from .errors import MarketMonitorNotFoundError
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
        }
        write_json_atomic(path, record)
        return MarketMonitorPromptDetail.model_validate(record)

    def list_prompts(self, run_id: str) -> list[MarketMonitorPromptSummary]:
        prompt_dir = self._run_prompt_root(run_id)
        if not prompt_dir.exists():
            return []
        items: list[MarketMonitorPromptSummary] = []
        for path in sorted(prompt_dir.glob("*/*.json")):
            payload = load_json(path)
            if payload is None:
                continue
            try:
                items.append(MarketMonitorPromptSummary.model_validate(payload))
            except Exception:
                continue
        items.sort(key=lambda item: item.created_at)
        return items

    def get_prompt(self, run_id: str, prompt_id: str) -> MarketMonitorPromptDetail:
        stage_key, attempt = _parse_prompt_id(prompt_id)
        path = self._prompt_dir(run_id, stage_key) / f"attempt-{attempt}.json"
        payload = load_json(path)
        if payload is None:
            raise MarketMonitorNotFoundError(prompt_id)
        return MarketMonitorPromptDetail.model_validate(payload)

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
