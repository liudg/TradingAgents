from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from shutil import rmtree

import pandas as pd
from pydantic import ValidationError

from tradingagents.default_config import DEFAULT_CONFIG
from .io_utils import load_json, write_dataframe_csv_atomic, write_json_atomic
from .schemas import MarketMonitorSymbolCacheMetadata, MarketMonitorSymbolCacheReadResult


MARKET_MONITOR_CACHE_DIR = Path(DEFAULT_CONFIG["data_cache_dir"]) / "market_monitor"
MARKET_MONITOR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
MARKET_MONITOR_SYMBOLS_DIR = MARKET_MONITOR_CACHE_DIR / "symbols"
MARKET_MONITOR_SYMBOLS_DIR.mkdir(parents=True, exist_ok=True)
_REQUIRED_OHLCV_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("^", "_idx_").replace("/", "_")


def _symbol_cache_dir(symbol: str) -> Path:
    return MARKET_MONITOR_SYMBOLS_DIR / _safe_symbol(symbol)


def _symbol_cache_meta_path(symbol: str) -> Path:
    return _symbol_cache_dir(symbol) / "meta.json"


def _symbol_cache_data_path(symbol: str) -> Path:
    return _symbol_cache_dir(symbol) / "daily.csv"


def _serialize_cache_frame(frame: pd.DataFrame) -> pd.DataFrame:
    serializable = frame.copy().reset_index()
    if "index" in serializable.columns and "Date" not in serializable.columns:
        serializable = serializable.rename(columns={"index": "Date"})
    return serializable


def _normalize_cache_frame(frame: pd.DataFrame, as_of_date: date | None = None) -> pd.DataFrame:
    if frame.empty or "Date" not in frame.columns:
        return pd.DataFrame(columns=_REQUIRED_OHLCV_COLUMNS)
    normalized = frame.copy()
    normalized["Date"] = pd.to_datetime(normalized["Date"], errors="coerce")
    normalized = normalized.dropna(subset=["Date"]).set_index("Date").sort_index()
    normalized.index = normalized.index.normalize()
    if as_of_date is not None:
        normalized = normalized[normalized.index <= pd.Timestamp(as_of_date)]
    keep_columns = [column for column in _REQUIRED_OHLCV_COLUMNS if column in normalized.columns]
    return normalized[keep_columns]


def _truncate_cache_frame(frame: pd.DataFrame, as_of_date: date) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame[frame.index <= pd.Timestamp(as_of_date)]


def _frame_content_hash(frame: pd.DataFrame) -> str:
    payload = _serialize_cache_frame(frame).to_csv(index=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_cache_frame_structurally_valid(frame: pd.DataFrame) -> tuple[bool, str | None]:
    if frame.empty:
        return False, "缓存数据为空"
    if not isinstance(frame.index, pd.DatetimeIndex):
        return False, "缓存索引不是 DatetimeIndex"
    if frame.index.has_duplicates:
        return False, "缓存索引存在重复日期"
    if not frame.index.is_monotonic_increasing:
        return False, "缓存索引未按日期升序排列"
    if not set(_REQUIRED_OHLCV_COLUMNS).issubset(frame.columns):
        return False, "缓存缺少必需列"
    return True, None


def load_symbol_daily_cache_record(symbol: str, as_of_date: date) -> MarketMonitorSymbolCacheReadResult:
    safe_symbol = _safe_symbol(symbol)
    cache_dir = _symbol_cache_dir(symbol)
    meta_path = _symbol_cache_meta_path(symbol)
    data_path = _symbol_cache_data_path(symbol)
    if not cache_dir.exists():
        return MarketMonitorSymbolCacheReadResult(state="cache_missing", symbol=symbol, safe_symbol=safe_symbol, frame=pd.DataFrame())
    if not meta_path.exists() or not data_path.exists():
        return MarketMonitorSymbolCacheReadResult(
            state="cache_corrupted",
            symbol=symbol,
            safe_symbol=safe_symbol,
            frame=pd.DataFrame(),
            reason="缓存目录缺少 meta.json 或 daily.csv",
        )
    try:
        payload = load_json(meta_path, raise_on_error=True)
    except Exception as exc:
        return MarketMonitorSymbolCacheReadResult(
            state="cache_corrupted",
            symbol=symbol,
            safe_symbol=safe_symbol,
            frame=pd.DataFrame(),
            reason=f"缓存元数据损坏: {exc}",
        )
    if payload is None:
        return MarketMonitorSymbolCacheReadResult(
            state="cache_corrupted",
            symbol=symbol,
            safe_symbol=safe_symbol,
            frame=pd.DataFrame(),
            reason="缓存元数据缺失",
        )
    try:
        metadata = MarketMonitorSymbolCacheMetadata.model_validate(payload)
    except ValidationError as exc:
        return MarketMonitorSymbolCacheReadResult(
            state="cache_corrupted",
            symbol=symbol,
            safe_symbol=safe_symbol,
            frame=pd.DataFrame(),
            reason=f"缓存元数据结构无效: {exc}",
        )
    try:
        raw_frame = pd.read_csv(data_path)
    except Exception as exc:
        return MarketMonitorSymbolCacheReadResult(
            state="cache_corrupted",
            symbol=symbol,
            safe_symbol=safe_symbol,
            frame=pd.DataFrame(),
            metadata=metadata,
            reason=f"缓存数据文件损坏: {exc}",
            last_successful_refresh_at=metadata.last_successful_refresh_at,
        )
    full_frame = _normalize_cache_frame(raw_frame)
    is_valid, reason = _is_cache_frame_structurally_valid(full_frame)
    cache_end_date = full_frame.index.max().date() if is_valid and not full_frame.empty else None
    frame = _truncate_cache_frame(full_frame, as_of_date)
    if frame.empty:
        return MarketMonitorSymbolCacheReadResult(
            state="cache_stale",
            symbol=symbol,
            safe_symbol=safe_symbol,
            frame=frame,
            metadata=metadata,
            reason="请求日期早于缓存覆盖范围",
            cache_end_date=cache_end_date,
            last_successful_refresh_at=metadata.last_successful_refresh_at,
        )
    if metadata.symbol != symbol or metadata.safe_symbol != safe_symbol:
        return MarketMonitorSymbolCacheReadResult(
            state="cache_corrupted",
            symbol=symbol,
            safe_symbol=safe_symbol,
            frame=frame,
            metadata=metadata,
            reason="缓存元数据与符号不匹配",
            cache_end_date=cache_end_date,
            last_successful_refresh_at=metadata.last_successful_refresh_at,
        )
    if is_valid:
        if metadata.trading_days != len(full_frame.index):
            return MarketMonitorSymbolCacheReadResult(
                state="cache_corrupted",
                symbol=symbol,
                safe_symbol=safe_symbol,
                frame=frame,
                metadata=metadata,
                reason="缓存元数据行数与数据文件不一致",
                cache_end_date=cache_end_date,
                last_successful_refresh_at=metadata.last_successful_refresh_at,
            )
        if metadata.date_range_start and metadata.date_range_start != full_frame.index.min().date():
            return MarketMonitorSymbolCacheReadResult(
                state="cache_corrupted",
                symbol=symbol,
                safe_symbol=safe_symbol,
                frame=frame,
                metadata=metadata,
                reason="缓存起始日期与元数据不一致",
                cache_end_date=cache_end_date,
                last_successful_refresh_at=metadata.last_successful_refresh_at,
            )
        if metadata.date_range_end and metadata.date_range_end != full_frame.index.max().date():
            return MarketMonitorSymbolCacheReadResult(
                state="cache_corrupted",
                symbol=symbol,
                safe_symbol=safe_symbol,
                frame=frame,
                metadata=metadata,
                reason="缓存结束日期与元数据不一致",
                cache_end_date=cache_end_date,
                last_successful_refresh_at=metadata.last_successful_refresh_at,
            )
        if metadata.content_hash and metadata.content_hash != _frame_content_hash(full_frame):
            return MarketMonitorSymbolCacheReadResult(
                state="cache_corrupted",
                symbol=symbol,
                safe_symbol=safe_symbol,
                frame=frame,
                metadata=metadata,
                reason="缓存内容摘要与元数据不一致",
                cache_end_date=cache_end_date,
                last_successful_refresh_at=metadata.last_successful_refresh_at,
            )
    return MarketMonitorSymbolCacheReadResult(
        state="cache_hit" if is_valid else "cache_invalid_structure",
        symbol=symbol,
        safe_symbol=safe_symbol,
        frame=frame,
        metadata=metadata,
        reason=reason,
        cache_end_date=cache_end_date,
        last_successful_refresh_at=metadata.last_successful_refresh_at,
    )


def save_symbol_daily_cache(
    symbol: str,
    frame: pd.DataFrame,
    *,
    as_of_date: date,
    expected_close_date: date,
    required_rows: int,
    source: str = "yfinance",
    now: datetime | None = None,
) -> None:
    if frame.empty:
        return
    normalized = frame.copy().sort_index()
    cache_dir = _symbol_cache_dir(symbol)
    temp_meta_path = cache_dir / "meta.json.tmp"
    if temp_meta_path.exists():
        temp_meta_path.unlink(missing_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now or datetime.now(timezone.utc)
    retention_days = int(DEFAULT_CONFIG.get("market_monitor_symbol_cache_retention_days", 30))
    metadata = MarketMonitorSymbolCacheMetadata(
        symbol=symbol,
        safe_symbol=_safe_symbol(symbol),
        created_at=timestamp,
        updated_at=timestamp,
        last_successful_refresh_at=timestamp,
        last_successful_as_of_date=as_of_date,
        expected_close_date=expected_close_date,
        date_range_start=normalized.index.min().date() if not normalized.empty else None,
        date_range_end=normalized.index.max().date() if not normalized.empty else None,
        trading_days=len(normalized.index),
        columns=list(normalized.columns),
        source=source,
        source_params={"required_rows": required_rows, "as_of_date": as_of_date.isoformat()},
        max_staleness_days=int(DEFAULT_CONFIG.get("market_monitor_symbol_cache_max_age_days", 3)),
        retention_expires_on=(normalized.index.max().date() if not normalized.empty else as_of_date) + timedelta(days=retention_days),
        content_hash=_frame_content_hash(normalized),
    )
    write_dataframe_csv_atomic(_symbol_cache_data_path(symbol), _serialize_cache_frame(normalized))
    write_json_atomic(_symbol_cache_meta_path(symbol), metadata.model_dump(mode="json"))


def evaluate_symbol_daily_cache(
    symbol: str,
    as_of_date: date,
    lookback_days: int,
    expected_close_date: date,
    now: datetime | None = None,
) -> MarketMonitorSymbolCacheReadResult:
    result = load_symbol_daily_cache_record(symbol, as_of_date)
    if result.state != "cache_hit":
        return result
    frame = result.frame if isinstance(result.frame, pd.DataFrame) else pd.DataFrame()
    metadata = result.metadata
    if metadata is None:
        return result.model_copy(update={"state": "cache_corrupted", "reason": "缓存元数据缺失"})
    if len(frame.index) < lookback_days:
        return result.model_copy(update={"state": "cache_invalid_structure", "reason": "缓存行数不足"})
    if result.cache_end_date is None or result.cache_end_date < expected_close_date:
        return result.model_copy(update={"state": "cache_stale", "reason": "缓存未覆盖预期收盘日"})
    reference = now or datetime.now(timezone.utc)
    max_age_days = float(metadata.max_staleness_days)
    age_days = max(0.0, (reference - metadata.last_successful_refresh_at).total_seconds() / 86400)
    if age_days > max_age_days:
        return result.model_copy(update={"state": "cache_stale", "reason": "缓存刷新时间超出允许范围"})
    return result


def cleanup_symbol_daily_cache(retention_days: int, now: datetime | None = None) -> int:
    if retention_days <= 0 or not MARKET_MONITOR_SYMBOLS_DIR.exists():
        return 0
    reference = (now or datetime.now(timezone.utc)).date()
    removed = 0
    for cache_dir in MARKET_MONITOR_SYMBOLS_DIR.iterdir():
        if not cache_dir.is_dir():
            continue
        meta_path = cache_dir / "meta.json"
        if not meta_path.exists():
            if (cache_dir / "meta.json.tmp").exists() or (cache_dir / "daily.csv.tmp").exists() or (cache_dir / "daily.csv").exists():
                continue
            rmtree(cache_dir, ignore_errors=True)
            removed += 1
            continue
        try:
            payload = load_json(meta_path, raise_on_error=True)
            metadata = MarketMonitorSymbolCacheMetadata.model_validate(payload)
        except Exception:
            rmtree(cache_dir, ignore_errors=True)
            removed += 1
            continue
        expires_on = metadata.retention_expires_on or ((metadata.date_range_end or metadata.last_successful_as_of_date) + timedelta(days=retention_days))
        if expires_on >= reference:
            continue
        rmtree(cache_dir, ignore_errors=True)
        removed += 1
    return removed
