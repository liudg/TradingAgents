from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .cache import MARKET_MONITOR_CACHE_DIR
from .run_store import MonitorRunStore
from .schemas import MarketMonitorPromptDetail, MarketMonitorPromptSummary


class PromptCaptureStore:
    def __init__(self, root: Path | None = None, run_store: MonitorRunStore | None = None) -> None:
        self.root = root or (MARKET_MONITOR_CACHE_DIR / "runs")
        self.run_store = run_store
        self.root.mkdir(parents=True, exist_ok=True)

    def capture_prompt(
        self,
        run_id: str,
        stage_key: str,
        attempt: int,
        model: str,
        payload: dict[str, Any],
    ) -> MarketMonitorPromptDetail:
        created_at = datetime.now()
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
        _write_json_atomic(path, record)
        return MarketMonitorPromptDetail.model_validate(record)

    def list_prompts(self, run_id: str) -> list[MarketMonitorPromptSummary]:
        prompt_dir = self._run_prompt_root(run_id)
        if not prompt_dir.exists():
            return []
        items: list[MarketMonitorPromptSummary] = []
        for path in sorted(prompt_dir.glob("*/*.json")):
            payload = _load_json(path)
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
        payload = _load_json(path)
        if payload is None:
            raise KeyError(prompt_id)
        return MarketMonitorPromptDetail.model_validate(payload)

    def _run_prompt_root(self, run_id: str) -> Path:
        if self.run_store is not None:
            return self.run_store.resolve_run_dir(run_id) / "prompts"
        return self.root / run_id / "prompts"

    def _prompt_dir(self, run_id: str, stage_key: str) -> Path:
        return self._run_prompt_root(run_id) / stage_key


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as handle:
        temp_path = Path(handle.name)
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    try:
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _parse_prompt_id(prompt_id: str) -> tuple[str, int]:
    stage_key, separator, attempt_text = prompt_id.rpartition("-attempt-")
    if not separator or not attempt_text.isdigit():
        raise KeyError(prompt_id)
    return stage_key, int(attempt_text)
