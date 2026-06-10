"""Structured yfinance news article fetchers for market-monitor workflows."""

from datetime import datetime
from typing import Optional

from dateutil.relativedelta import relativedelta

from tradingagents.dataflows import yfinance_proxy as yf
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.stockstats_utils import yf_retry
from tradingagents.dataflows.yfinance_news import _extract_article_data


def _article_in_window(article: dict, start_dt: datetime, end_dt: datetime) -> bool:
    pub_date = article.get("pub_date")
    if not pub_date:
        return True
    if hasattr(pub_date, "replace"):
        pub_date = pub_date.replace(tzinfo=None)
    return start_dt <= pub_date <= end_dt + relativedelta(days=1)


def fetch_ticker_news_articles_yfinance(
    ticker: str,
    start_date: str,
    end_date: str,
    limit: int,
) -> list[dict]:
    """Fetch structured ticker news articles from yfinance."""
    stock = yf.Ticker(ticker)
    news = yf_retry(lambda: stock.get_news(count=limit))
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    articles = []
    for raw_article in news or []:
        article = _extract_article_data(raw_article)
        if not _article_in_window(article, start_dt, end_dt):
            continue
        article["ticker"] = ticker
        articles.append(article)
        if len(articles) >= limit:
            break
    return articles


def fetch_global_news_articles_yfinance(
    curr_date: str,
    look_back_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    """Fetch structured global/macro news articles from yfinance Search."""
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - relativedelta(days=look_back_days)
    articles = []
    seen_titles = set()
    for query in config["global_news_queries"]:
        search = yf_retry(lambda q=query: yf.Search(
            query=q,
            news_count=limit,
            enable_fuzzy_query=True,
        ))
        for raw_article in search.news or []:
            article = _extract_article_data(raw_article)
            title = article.get("title")
            if not title or title in seen_titles:
                continue
            if not _article_in_window(article, start_dt, curr_dt):
                continue
            seen_titles.add(title)
            articles.append(article)
            if len(articles) >= limit:
                return articles
    return articles
