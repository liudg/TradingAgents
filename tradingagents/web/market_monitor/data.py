from __future__ import annotations

import logging
from datetime import date, timedelta
import time
from typing import Dict, Iterable

import pandas as pd
from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows.yfinance_proxy import get_yf
from .cache import load_symbol_daily_cache, save_symbol_daily_cache

logger = logging.getLogger(__name__)

YFINANCE_DOWNLOAD_TIMEOUT_SECONDS = 10


def _normalize_ohlcv_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    result = frame.copy()
    if isinstance(result.index, pd.DatetimeIndex) and result.index.tz is not None:
        result.index = result.index.tz_localize(None)
    keep_columns = [column for column in ["Open", "High", "Low", "Close", "Volume"] if column in result.columns]
    result = result[keep_columns].dropna(how="all")
    result.index = pd.to_datetime(result.index).normalize()
    return result


def fetch_daily_history(
    symbols: Iterable[str],
    as_of_date: date,
    lookback_days: int = 420,
    force_refresh: bool = False,
) -> Dict[str, pd.DataFrame]:
    symbol_list = list(dict.fromkeys(symbols))

    result: Dict[str, pd.DataFrame] = {}
    for symbol in symbol_list:
        frame, fetched_live = _get_symbol_history(symbol, as_of_date, lookback_days, force_refresh=force_refresh)
        result[symbol] = frame
        if fetched_live:
            time.sleep(0.25)
    return result


def _get_symbol_history(
    symbol: str,
    as_of_date: date,
    lookback_days: int,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, bool]:
    if not force_refresh:
        cached = load_symbol_daily_cache(symbol, as_of_date)
        if _is_cache_usable(cached, as_of_date, lookback_days):
            return cached, False

    fresh = _download_single_symbol(symbol, as_of_date, lookback_days)
    if not fresh.empty:
        save_symbol_daily_cache(symbol, fresh)
        return fresh, True

    if not force_refresh:
        return load_symbol_daily_cache(symbol, as_of_date), False
    return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]), False


def _is_cache_usable(frame: pd.DataFrame, as_of_date: date, lookback_days: int) -> bool:
    if frame.empty:
        return False
    if not isinstance(frame.index, pd.DatetimeIndex):
        return False
    required_start = pd.Timestamp(as_of_date - timedelta(days=lookback_days))
    cached_start = frame.index.min()
    cached_end = frame.index.max()
    if pd.isna(cached_start) or pd.isna(cached_end):
        return False
    if cached_start > required_start:
        return False
    return cached_end >= _expected_market_close_date(as_of_date)


def _expected_market_close_date(as_of_date: date) -> pd.Timestamp:
    target = pd.Timestamp(as_of_date)
    while not _is_us_market_trading_day(target.date()):
        target -= pd.Timedelta(days=1)
    return target


def _is_us_market_trading_day(target: date) -> bool:
    return target.weekday() < 5 and target not in _us_market_holidays(target.year)


def _us_market_holidays(year: int) -> set[date]:
    return {
        _observed_date(date(year, 1, 1)),
        _nth_weekday_of_month(year, 1, 0, 3),
        _nth_weekday_of_month(year, 2, 0, 3),
        _good_friday(year),
        _last_weekday_of_month(year, 5, 0),
        _observed_date(date(year, 6, 19)),
        _observed_date(date(year, 7, 4)),
        _nth_weekday_of_month(year, 9, 0, 1),
        _nth_weekday_of_month(year, 11, 3, 4),
        _observed_date(date(year, 12, 25)),
    }


def _observed_date(target: date) -> date:
    if target.weekday() == 5:
        return target - timedelta(days=1)
    if target.weekday() == 6:
        return target + timedelta(days=1)
    return target


def _nth_weekday_of_month(year: int, month: int, weekday: int, occurrence: int) -> date:
    first_day = date(year, month, 1)
    day_offset = (weekday - first_day.weekday()) % 7
    return first_day + timedelta(days=day_offset + (occurrence - 1) * 7)


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _good_friday(year: int) -> date:
    easter = _easter_sunday(year)
    return easter - timedelta(days=2)


def _easter_sunday(year: int) -> date:
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _download_single_symbol(symbol: str, as_of_date: date, lookback_days: int) -> pd.DataFrame:
    yf = get_yf()
    start = as_of_date - timedelta(days=lookback_days)
    end = as_of_date + timedelta(days=1)
    for attempt in range(3):
        try:
            raw = yf.download(
                tickers=symbol,
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=False,
                progress=False,
                threads=False,
                multi_level_index=False,
                timeout=YFINANCE_DOWNLOAD_TIMEOUT_SECONDS,
            )
            normalized = _normalize_ohlcv_frame(raw)
            if not normalized.empty:
                return normalized
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        except YFRateLimitError:
            time.sleep(1.5 * (attempt + 1))
        except Exception:
            logger.warning("下载 %s 日线数据失败", symbol, exc_info=True)
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])


def build_market_dataset(
    universe: dict[str, list[str]],
    as_of_date: date,
    force_refresh: bool = False,
) -> dict[str, Dict[str, pd.DataFrame]]:
    core_and_sector = universe["core_index_etfs"] + universe["sector_etfs"] + ["^VIX"]
    return {
        "core": fetch_daily_history(core_and_sector, as_of_date, force_refresh=force_refresh),
    }
