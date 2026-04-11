from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable
from typing import Any

import pandas as pd

from tradingagents.default_config import DEFAULT_CONFIG


MARKET_MONITOR_CACHE_DIR = Path(DEFAULT_CONFIG["data_cache_dir"]) / "market_monitor"
MARKET_MONITOR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOT_CACHE_VERSION = 1


def _symbol_cache_path(symbol: str) -> Path:
    safe_symbol = symbol.replace("^", "_idx_").replace("/", "_")
    return MARKET_MONITOR_CACHE_DIR / f"{safe_symbol}_daily.csv"


def _snapshot_cache_path(as_of_date: date) -> Path:
    return MARKET_MONITOR_CACHE_DIR / f"snapshot_{as_of_date.isoformat()}.json"


def load_symbol_daily_cache(symbol: str, as_of_date: date) -> pd.DataFrame:
    path = _symbol_cache_path(symbol)
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    if frame.empty or "Date" not in frame.columns:
        return pd.DataFrame()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date"]).set_index("Date").sort_index()
    frame.index = frame.index.normalize()
    return frame[frame.index <= pd.Timestamp(as_of_date)]


def save_symbol_daily_cache(symbol: str, frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    path = _symbol_cache_path(symbol)
    serializable = frame.copy().reset_index()
    if "index" in serializable.columns and "Date" not in serializable.columns:
        serializable = serializable.rename(columns={"index": "Date"})
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as handle:
        temp_path = Path(handle.name)
    try:
        serializable.to_csv(temp_path, index=False)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def load_snapshot_cache(as_of_date: date) -> dict[str, Any] | None:
    path = _snapshot_cache_path(as_of_date)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("cache_version") != SNAPSHOT_CACHE_VERSION:
        return None
    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        return None
    return snapshot


def save_snapshot_cache(as_of_date: date, payload: dict[str, Any]) -> None:
    path = _snapshot_cache_path(as_of_date)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as handle:
        temp_path = Path(handle.name)
        handle.write(
            json.dumps(
                {
                    "cache_version": SNAPSHOT_CACHE_VERSION,
                    "snapshot": payload,
                },
                ensure_ascii=False,
                indent=2,
                default=_json_default,
            )
        )
    try:
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def symbol_cache_status(symbol: str) -> dict[str, Any]:
    path = _symbol_cache_path(symbol)
    if not path.exists():
        return {"exists": False}
    return {
        "exists": True,
        "path": str(path),
        "updated_at": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(),
    }


def latest_symbol_cache_mtime(symbols: Iterable[str]) -> datetime | None:
    latest: float | None = None
    for symbol in symbols:
        path = _symbol_cache_path(symbol)
        if not path.exists():
            continue
        modified = os.path.getmtime(path)
        if latest is None or modified > latest:
            latest = modified
    if latest is None:
        return None
    return datetime.fromtimestamp(latest)
