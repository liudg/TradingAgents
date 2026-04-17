from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

ATOMIC_REPLACE_RETRY_DELAYS_SECONDS = (0.05, 0.15, 0.3)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _reserve_temp_path(path: Path, suffix: str = ".tmp") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(delete=False, dir=path.parent, suffix=suffix) as handle:
        return Path(handle.name)


def replace_file_atomic(source: Path, target: Path) -> None:
    attempts = len(ATOMIC_REPLACE_RETRY_DELAYS_SECONDS) + 1
    for attempt in range(attempts):
        try:
            source.replace(target)
            return
        except PermissionError:
            if attempt >= attempts - 1:
                raise
            time.sleep(ATOMIC_REPLACE_RETRY_DELAYS_SECONDS[attempt])


def write_text_atomic(path: Path, content: str, encoding: str = "utf-8") -> None:
    temp_path = _reserve_temp_path(path)
    try:
        temp_path.write_text(content, encoding=encoding)
        replace_file_atomic(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    write_text_atomic(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
    )


def write_dataframe_csv_atomic(path: Path, frame: Any) -> None:
    temp_path = _reserve_temp_path(path)
    try:
        frame.to_csv(temp_path, index=False)
        replace_file_atomic(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def extract_json_payload(content: str) -> dict[str, Any] | None:
    stripped = content.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(stripped[start : end + 1])
    except json.JSONDecodeError:
        return None
