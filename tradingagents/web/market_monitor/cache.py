from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from tradingagents.default_config import DEFAULT_CONFIG
from .io_utils import write_dataframe_csv_atomic


MARKET_MONITOR_CACHE_DIR = Path(DEFAULT_CONFIG["data_cache_dir"]) / "market_monitor"
MARKET_MONITOR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
MARKET_MONITOR_DATA_DIR = MARKET_MONITOR_CACHE_DIR / "data"
MARKET_MONITOR_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _symbol_cache_path(symbol: str) -> Path:
    safe_symbol = symbol.replace("^", "_idx_").replace("/", "_")
    return MARKET_MONITOR_DATA_DIR / f"{safe_symbol}.csv"


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
    write_dataframe_csv_atomic(path, serializable)
