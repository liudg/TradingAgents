from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable
from urllib.parse import urlparse

import pandas as pd
from yfinance.exceptions import YFRateLimitError

from tradingagents.dataflows.yfinance_news import fetch_global_news_articles_yfinance, fetch_ticker_news_articles_yfinance
from tradingagents.dataflows.yfinance_proxy import get_yf
from .cache import evaluate_symbol_daily_cache, save_symbol_daily_cache

logger = logging.getLogger(__name__)

YFINANCE_DOWNLOAD_TIMEOUT_SECONDS = 10
MIN_REQUIRED_TRADING_DAYS = 252
NEWS_LOOKBACK_DAYS = 7
GLOBAL_NEWS_LIMIT = 10
TICKER_NEWS_LIMIT = 3
MARKET_EVENT_NEWS_SYMBOLS = ["SPY", "QQQ", "IWM", "DIA", "^VIX", "LQD", "JNK"]


@dataclass(frozen=True)
class SymbolHistoryResult:
    frame: pd.DataFrame
    cache_state: str
    result_state: str
    fetched_live: bool
    expected_close_date: pd.Timestamp
    reason: str | None = None
    cache_end_date: str | None = None
    last_successful_refresh_at: str | None = None


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
) -> tuple[Dict[str, pd.DataFrame], dict[str, Any]]:
    symbol_list = list(dict.fromkeys(symbols))

    result: Dict[str, pd.DataFrame] = {}
    symbol_summaries: list[dict[str, Any]] = []
    counts = {
        "cache_missing": 0,
        "cache_corrupted": 0,
        "cache_invalid_structure": 0,
        "cache_stale": 0,
        "cache_hit": 0,
    }
    result_counts = {
        "cache_hit": 0,
        "refreshed": 0,
        "stale_fallback": 0,
        "empty": 0,
    }
    for symbol in symbol_list:
        history = _get_symbol_history(symbol, as_of_date, lookback_days, force_refresh=force_refresh)
        result[symbol] = history.frame
        if history.fetched_live:
            time.sleep(0.25)
        counts[history.cache_state] = counts.get(history.cache_state, 0) + 1
        result_counts[history.result_state] = result_counts.get(history.result_state, 0) + 1
        symbol_summaries.append(
            {
                "symbol": symbol,
                "cache_state": history.cache_state,
                "result_state": history.result_state,
                "rows": int(len(history.frame.index)) if isinstance(history.frame.index, pd.Index) else 0,
                "expected_close_date": history.expected_close_date.date().isoformat(),
                "cache_end_date": history.cache_end_date,
                "last_successful_refresh_at": history.last_successful_refresh_at,
                "reason": history.reason,
            }
        )
    return result, {
        "force_refresh": force_refresh,
        "symbols": symbol_summaries,
        "counts": counts,
        "result_counts": result_counts,
    }


def _get_symbol_history(
    symbol: str,
    as_of_date: date,
    lookback_days: int,
    force_refresh: bool = False,
) -> SymbolHistoryResult:
    expected_close_date = _expected_market_close_date(as_of_date)
    required_rows = _required_trading_days(lookback_days)
    cache_result = evaluate_symbol_daily_cache(symbol, as_of_date, required_rows, expected_close_date.date())
    if not force_refresh and cache_result.state == "cache_hit":
        return SymbolHistoryResult(
            frame=cache_result.frame,
            cache_state="cache_hit",
            result_state="cache_hit",
            fetched_live=False,
            expected_close_date=expected_close_date,
            reason=cache_result.reason,
            cache_end_date=cache_result.cache_end_date.isoformat() if cache_result.cache_end_date else None,
            last_successful_refresh_at=cache_result.last_successful_refresh_at.isoformat() if cache_result.last_successful_refresh_at else None,
        )

    fresh = _download_single_symbol(symbol, as_of_date, lookback_days)
    if not fresh.empty:
        save_symbol_daily_cache(
            symbol,
            fresh,
            as_of_date=as_of_date,
            expected_close_date=expected_close_date.date(),
            required_rows=required_rows,
        )
        return SymbolHistoryResult(
            frame=fresh,
            cache_state=cache_result.state,
            result_state="refreshed",
            fetched_live=True,
            expected_close_date=expected_close_date,
            cache_end_date=fresh.index.max().date().isoformat() if not fresh.empty else None,
            reason=cache_result.reason,
            last_successful_refresh_at=cache_result.last_successful_refresh_at.isoformat() if cache_result.last_successful_refresh_at else None,
        )

    if cache_result.state == "cache_stale" and isinstance(cache_result.frame, pd.DataFrame) and not cache_result.frame.empty:
        return SymbolHistoryResult(
            frame=cache_result.frame,
            cache_state="cache_stale",
            result_state="stale_fallback",
            fetched_live=False,
            expected_close_date=expected_close_date,
            reason=cache_result.reason,
            cache_end_date=cache_result.cache_end_date.isoformat() if cache_result.cache_end_date else None,
            last_successful_refresh_at=cache_result.last_successful_refresh_at.isoformat() if cache_result.last_successful_refresh_at else None,
        )
    if cache_result.state in {"cache_missing", "cache_corrupted", "cache_invalid_structure", "cache_stale"}:
        return SymbolHistoryResult(
            frame=pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]),
            cache_state=cache_result.state,
            result_state="empty",
            fetched_live=False,
            expected_close_date=expected_close_date,
            reason=cache_result.reason,
            cache_end_date=cache_result.cache_end_date.isoformat() if cache_result.cache_end_date else None,
            last_successful_refresh_at=cache_result.last_successful_refresh_at.isoformat() if cache_result.last_successful_refresh_at else None,
        )
    return SymbolHistoryResult(
        frame=pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]),
        cache_state=cache_result.state,
        result_state="empty",
        fetched_live=False,
        expected_close_date=expected_close_date,
        reason=cache_result.reason,
        cache_end_date=cache_result.cache_end_date.isoformat() if cache_result.cache_end_date else None,
        last_successful_refresh_at=cache_result.last_successful_refresh_at.isoformat() if cache_result.last_successful_refresh_at else None,
    )


def _required_trading_days(lookback_days: int) -> int:
    return max(MIN_REQUIRED_TRADING_DAYS, math.ceil(lookback_days * 0.7))


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


def _fetch_event_news(universe: dict[str, list[str]], as_of_date: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    generated_at = datetime.now(timezone.utc)
    errors: list[str] = []
    articles: list[dict[str, Any]] = []
    global_news_count = 0
    try:
        global_articles = fetch_global_news_articles_yfinance(as_of_date.isoformat(), NEWS_LOOKBACK_DAYS, GLOBAL_NEWS_LIMIT)
        global_news_count = len(global_articles)
        articles.extend(global_articles)
    except Exception as exc:
        logger.warning("获取全球市场新闻失败", exc_info=True)
        errors.append(f"global_news: {exc}")

    ticker_news_count = 0
    start_date = (as_of_date - timedelta(days=NEWS_LOOKBACK_DAYS)).isoformat()
    end_date = as_of_date.isoformat()
    monitored_symbols = set(universe["core_index_etfs"] + ["^VIX", "LQD", "JNK"])
    news_symbols = [symbol for symbol in MARKET_EVENT_NEWS_SYMBOLS if symbol in monitored_symbols]
    for symbol in news_symbols:
        try:
            ticker_articles = fetch_ticker_news_articles_yfinance(symbol, start_date, end_date, TICKER_NEWS_LIMIT)
            ticker_news_count += len(ticker_articles)
            articles.extend(ticker_articles)
        except Exception as exc:
            logger.warning("获取 %s 新闻失败", symbol, exc_info=True)
            errors.append(f"ticker_news.{symbol}: {exc}")

    candidates = _event_fact_candidates_from_articles(articles, universe, generated_at)
    return candidates, {
        "source": "yfinance_news",
        "generated_at": generated_at.isoformat(),
        "global_news_count": global_news_count,
        "ticker_news_count": ticker_news_count,
        "event_fact_candidate_count": len(candidates),
        "errors": errors,
    }


def _event_fact_candidates_from_articles(
    articles: list[dict[str, Any]],
    universe: dict[str, list[str]],
    generated_at: datetime,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for article in articles:
        candidate = _article_to_event_fact_candidate(article, universe, generated_at)
        if candidate is None:
            continue
        key = (candidate["event"].lower(), candidate["source_url"])
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return candidates


def _article_to_event_fact_candidate(
    article: dict[str, Any],
    universe: dict[str, list[str]],
    generated_at: datetime,
) -> dict[str, Any] | None:
    title = _clean_article_text(article.get("title"))
    source_name = _clean_article_text(article.get("publisher"))
    source_url = _clean_article_text(article.get("link"))
    if not title or title == "No title" or not source_name or source_name == "Unknown" or not _is_auditable_url(source_url):
        return None
    summary = _clean_article_text(article.get("summary")) or title
    observed_at, has_observed_at = _article_observed_at(article.get("pub_date"), generated_at)
    expires_at = observed_at + timedelta(days=1)
    confidence = _article_confidence(source_name, has_observed_at)
    return {
        "event": title,
        "scope": _article_scope(article, universe),
        "severity": _article_severity(f"{title} {summary}"),
        "source_type": "news",
        "source_name": source_name,
        "source_url": source_url,
        "source_summary": summary,
        "observed_at": observed_at.isoformat(),
        "confidence": confidence,
        "expires_at": expires_at.isoformat(),
    }


def _article_observed_at(value: Any, generated_at: datetime) -> tuple[datetime, bool]:
    if isinstance(value, datetime):
        observed_at = value
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        return observed_at, True
    return generated_at, False


def _article_scope(article: dict[str, Any], universe: dict[str, list[str]]) -> str:
    ticker = _clean_article_text(article.get("ticker")).upper()
    if ticker in {symbol.upper() for symbol in universe.get("sector_etfs", [])}:
        return "sector_level"
    if ticker in {"^VIX", "LQD", "JNK"}:
        return "cross_asset"
    if ticker:
        return "index_level"
    return "index_level"


def _article_severity(text: str) -> str:
    normalized = text.lower()
    if any(token in normalized for token in ("war", "invasion", "default", "banking crisis", "emergency", "crash", "systemic", "shutdown")):
        return "critical"
    if any(token in normalized for token in ("fed", "fomc", "cpi", "inflation", "rates", "jobs", "payrolls", "tariff", "sanctions", "oil shock")):
        return "high"
    if any(token in normalized for token in ("volatility", "guidance", "sector rotation", "market outlook")):
        return "medium"
    return "medium"


def _article_confidence(source_name: str, has_observed_at: bool) -> float:
    normalized = source_name.lower()
    confidence = 0.78 if any(token in normalized for token in ("reuters", "bloomberg", "cnbc", "marketwatch", "wsj", "yahoo")) else 0.68
    if not has_observed_at:
        confidence -= 0.08
    return round(max(0.55, min(0.85, confidence)), 2)


def _is_auditable_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _clean_article_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def build_market_dataset(
    universe: dict[str, list[str]],
    as_of_date: date,
    force_refresh: bool = False,
    include_event_news: bool = True,
) -> dict[str, Any]:
    core_and_sector = universe["core_index_etfs"] + universe["sector_etfs"] + ["^VIX"]
    core, cache_summary = fetch_daily_history(core_and_sector, as_of_date, force_refresh=force_refresh)
    if include_event_news:
        event_fact_candidates, search_status = _fetch_event_news(universe, as_of_date)
    else:
        event_fact_candidates = []
        search_status = {
            "source": "disabled_for_history",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "global_news_count": 0,
            "ticker_news_count": 0,
            "event_fact_candidate_count": 0,
            "errors": [],
        }
    return {
        "core": core,
        "cache_summary": cache_summary,
        "search": {
            "event_fact_candidates": event_fact_candidates,
            "status": search_status,
        },
    }
