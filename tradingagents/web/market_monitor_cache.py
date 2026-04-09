from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from tradingagents.default_config import DEFAULT_CONFIG


MARKET_MONITOR_CACHE_DIR = Path(DEFAULT_CONFIG["data_cache_dir"]) / "market_monitor"
MARKET_MONITOR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
LEGACY_CACHE_DIR = Path(DEFAULT_CONFIG["data_cache_dir"])


def _symbol_cache_path(symbol: str) -> Path:
    safe_symbol = symbol.replace("^", "_idx_").replace("/", "_")
    return MARKET_MONITOR_CACHE_DIR / f"{safe_symbol}_daily.csv"


def _snapshot_cache_path(as_of_date: date) -> Path:
    return MARKET_MONITOR_CACHE_DIR / f"snapshot_{as_of_date.isoformat()}.json"


def load_symbol_daily_cache(symbol: str, as_of_date: date) -> pd.DataFrame:
    path = _symbol_cache_path(symbol)
    if path.exists():
        frame = pd.read_csv(path)
    else:
        legacy = _load_legacy_symbol_cache(symbol)
        if legacy.empty:
            return pd.DataFrame()
        frame = legacy.reset_index().rename(columns={"index": "Date"})
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
    serializable.to_csv(path, index=False)


def load_snapshot_cache(as_of_date: date) -> dict[str, Any] | None:
    path = _snapshot_cache_path(as_of_date)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_snapshot_cache(as_of_date: date, payload: dict[str, Any]) -> None:
    path = _snapshot_cache_path(as_of_date)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


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


def _load_legacy_symbol_cache(symbol: str) -> pd.DataFrame:
    pattern = f"{symbol}-YFin-data-*.csv"
    candidates = sorted(LEGACY_CACHE_DIR.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        return pd.DataFrame()
    try:
        frame = pd.read_csv(candidates[0])
    except Exception:
        return pd.DataFrame()
    if frame.empty:
        return pd.DataFrame()
    if "Date" in frame.columns:
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame = frame.dropna(subset=["Date"]).set_index("Date").sort_index()
        frame.index = frame.index.normalize()
    return frame
