from __future__ import annotations

from datetime import date, timedelta
import os
import time
from typing import Dict, Iterable

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError


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


def _configure_yfinance_proxy() -> None:
    proxy_url = os.getenv("YFINANCE_PROXY", "").strip()
    http_proxy = os.getenv("YFINANCE_HTTP_PROXY", "").strip()
    https_proxy = os.getenv("YFINANCE_HTTPS_PROXY", "").strip()

    if proxy_url:
        yf.config.network.proxy = {"http": proxy_url, "https": proxy_url}
        return
    if http_proxy or https_proxy:
        yf.config.network.proxy = {
            "http": http_proxy or https_proxy,
            "https": https_proxy or http_proxy,
        }
        return
    yf.config.network.proxy = None


def fetch_daily_history(
    symbols: Iterable[str],
    as_of_date: date,
    lookback_days: int = 420,
) -> Dict[str, pd.DataFrame]:
    symbol_list = list(dict.fromkeys(symbols))
    _configure_yfinance_proxy()

    result: Dict[str, pd.DataFrame] = {}
    for symbol in symbol_list:
        result[symbol] = _download_single_symbol(symbol, as_of_date, lookback_days)
        time.sleep(0.25)
    return result


def _download_single_symbol(symbol: str, as_of_date: date, lookback_days: int) -> pd.DataFrame:
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
            )
            normalized = _normalize_ohlcv_frame(raw)
            if not normalized.empty:
                return normalized
            time.sleep(1.0 * (attempt + 1))
        except YFRateLimitError:
            time.sleep(1.5 * (attempt + 1))
        except Exception:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])


def build_market_dataset(universe: dict[str, list[str]], as_of_date: date) -> dict[str, Dict[str, pd.DataFrame]]:
    core_and_sector = universe["core_index_etfs"] + universe["sector_etfs"] + ["^VIX"]
    return {
        "core": fetch_daily_history(core_and_sector, as_of_date),
        "nasdaq_100": fetch_daily_history(universe["nasdaq_100"], as_of_date),
    }
