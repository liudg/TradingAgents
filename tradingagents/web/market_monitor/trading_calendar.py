from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo

MARKET_TIMEZONE = ZoneInfo("America/New_York")
MARKET_CLOSE_TIME = dt_time(16, 0)


def market_now_eastern() -> datetime:
    return datetime.now(MARKET_TIMEZONE)


def latest_complete_us_trading_day(now: datetime | None = None) -> date:
    current = _as_eastern(now) if now is not None else market_now_eastern()
    current_date = current.date()
    if is_us_market_trading_day(current_date) and current.time() >= MARKET_CLOSE_TIME:
        return current_date
    return previous_us_trading_day(current_date - timedelta(days=1))


def previous_us_trading_day(start: date) -> date:
    cursor = start
    while not is_us_market_trading_day(cursor):
        cursor -= timedelta(days=1)
    return cursor


def expected_market_close_date(as_of_date: date) -> date:
    return previous_us_trading_day(as_of_date)


def is_us_market_trading_day(target: date) -> bool:
    return target.weekday() < 5 and target not in us_market_holidays(target.year)


def resolve_market_monitor_as_of_date(as_of_date: date | None, data_mode: str = "daily") -> date:
    if as_of_date is not None:
        return as_of_date
    return latest_complete_us_trading_day()


def validate_market_monitor_as_of_date(as_of_date: date | None, data_mode: str) -> None:
    if as_of_date is None:
        return
    if data_mode == "daily":
        latest_complete = latest_complete_us_trading_day()
        if as_of_date > latest_complete:
            raise ValueError("as_of_date 不能晚于最近完整美股交易日（美东）")
        return
    current_eastern_date = market_now_eastern().date()
    if as_of_date > current_eastern_date:
        raise ValueError("盘中模式 as_of_date 不能晚于当前美东日期")


def us_market_holidays(year: int) -> set[date]:
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


def _as_eastern(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=MARKET_TIMEZONE)
    return value.astimezone(MARKET_TIMEZONE)


def _observed_date(target: date) -> date:
    if target.weekday() == 5:
        return target - timedelta(days=1)
    if target.weekday() == 6:
        return target + timedelta(days=1)
    return target


def _nth_weekday_of_month(year: int, month: int, weekday: int, nth: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current + timedelta(days=7 * (nth - 1))


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    if month == 12:
        current = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        current = date(year, month + 1, 1) - timedelta(days=1)
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def _good_friday(year: int) -> date:
    return _easter_sunday(year) - timedelta(days=2)


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
