from contextlib import contextmanager
from datetime import datetime
from typing import Annotated

import pandas as pd
from dateutil.relativedelta import relativedelta
from stockstats import wrap

from .config import get_config


INDICATOR_DESCRIPTIONS = {
    "close_50_sma": (
        "50 SMA: A medium-term trend indicator. "
        "Usage: Identify trend direction and serve as dynamic support/resistance. "
        "Tips: It lags price; combine with faster indicators for timely signals."
    ),
    "close_200_sma": (
        "200 SMA: A long-term trend benchmark. "
        "Usage: Confirm overall market trend and identify golden/death cross setups. "
        "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
    ),
    "close_10_ema": (
        "10 EMA: A responsive short-term average. "
        "Usage: Capture quick shifts in momentum and potential entry points. "
        "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
    ),
    "macd": (
        "MACD: Computes momentum via differences of EMAs. "
        "Usage: Look for crossovers and divergence as signals of trend changes. "
        "Tips: Confirm with other indicators in low-volatility or sideways markets."
    ),
    "macds": (
        "MACD Signal: An EMA smoothing of the MACD line. "
        "Usage: Use crossovers with the MACD line to trigger trades. "
        "Tips: Should be part of a broader strategy to avoid false positives."
    ),
    "macdh": (
        "MACD Histogram: Shows the gap between the MACD line and its signal. "
        "Usage: Visualize momentum strength and spot divergence early. "
        "Tips: Can be volatile; complement with additional filters in fast-moving markets."
    ),
    "rsi": (
        "RSI: Measures momentum to flag overbought/oversold conditions. "
        "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
        "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
    ),
    "boll": (
        "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
        "Usage: Acts as a dynamic benchmark for price movement. "
        "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
    ),
    "boll_ub": (
        "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
        "Usage: Signals potential overbought conditions and breakout zones. "
        "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
    ),
    "boll_lb": (
        "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
        "Usage: Indicates potential oversold conditions. "
        "Tips: Use additional analysis to avoid false reversal signals."
    ),
    "atr": (
        "ATR: Averages true range to measure volatility. "
        "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
        "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
    ),
    "vwma": (
        "VWMA: A moving average weighted by volume. "
        "Usage: Confirm trends by integrating price action with volume data. "
        "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
    ),
    "mfi": (
        "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure "
        "buying and selling pressure. "
        "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends "
        "or reversals. "
        "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate "
        "potential reversals."
    ),
}


def _import_futu():
    try:
        from futu import AuType, KLType, KL_FIELD, OpenQuoteContext, RET_OK, Session
    except ImportError as exc:
        raise RuntimeError(
            "Futu vendor requires the Python SDK. Install it with `pip install futu-api` "
            "and make sure OpenD is running."
        ) from exc

    return {
        "AuType": AuType,
        "KLType": KLType,
        "KL_FIELD": KL_FIELD,
        "OpenQuoteContext": OpenQuoteContext,
        "RET_OK": RET_OK,
        "Session": Session,
    }


def _normalize_futu_code(symbol: str) -> str:
    """Convert common ticker formats to Futu's market-prefixed code format."""
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("Symbol cannot be empty")

    if normalized.startswith(("US.", "HK.", "SH.", "SZ.")):
        return normalized

    if "." not in normalized:
        return f"US.{normalized}"

    left, right = normalized.rsplit(".", 1)

    if right == "HK":
        if left.isdigit():
            left = left.zfill(5)
        return f"HK.{left}"

    if right in {"SS", "SH"}:
        return f"SH.{left}"

    if right == "SZ":
        return f"SZ.{left}"

    # Handle US share classes like BRK.B while rejecting unsupported exchange suffixes like 7203.T.
    if left.isalpha() and right.isalpha() and len(right) <= 2:
        return f"US.{left}.{right}"

    raise ValueError(
        f"Unsupported Futu symbol format '{symbol}'. Use US.AAPL, HK.00700, 0700.HK, 600519.SS, or 000001.SZ."
    )


def _quote_session_for_code(code: str):
    futu = _import_futu()
    if code.startswith("US."):
        return futu["Session"].ALL
    return futu["Session"].NONE


@contextmanager
def _open_quote_context():
    futu = _import_futu()
    config = get_config()
    quote_ctx = futu["OpenQuoteContext"](
        host=config.get("futu_opend_host", "127.0.0.1"),
        port=config.get("futu_opend_port", 11111),
    )
    try:
        yield quote_ctx
    finally:
        quote_ctx.close()


def _history_to_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"])

    result = data.rename(
        columns={
            "time_key": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    ).copy()
    result["Date"] = pd.to_datetime(result["Date"], errors="coerce").dt.tz_localize(None)
    result = result.dropna(subset=["Date", "Close"])
    result["Adj Close"] = result["Close"]
    result = result[["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]]

    for col in ["Open", "High", "Low", "Close", "Adj Close"]:
        result[col] = pd.to_numeric(result[col], errors="coerce").round(2)
    result["Volume"] = pd.to_numeric(result["Volume"], errors="coerce").fillna(0).astype("int64")

    return result


def _fetch_history_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    futu = _import_futu()
    code = _normalize_futu_code(symbol)
    session = _quote_session_for_code(code)
    frames = []
    page_req_key = None

    with _open_quote_context() as quote_ctx:
        while True:
            ret, data, page_req_key = quote_ctx.request_history_kline(
                code,
                start=start_date,
                end=end_date,
                ktype=futu["KLType"].K_DAY,
                autype=futu["AuType"].QFQ,
                fields=[futu["KL_FIELD"].ALL],
                max_count=1000,
                page_req_key=page_req_key,
                session=session,
            )

            if ret != futu["RET_OK"]:
                raise RuntimeError(f"Futu request_history_kline failed for {code}: {data}")

            if data is not None and not data.empty:
                frames.append(data)

            if page_req_key is None:
                break

    if not frames:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"])

    history = pd.concat(frames, ignore_index=True)
    history = _history_to_ohlcv(history)
    history = history.sort_values("Date")
    return history


def get_stock(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    try:
        data = _fetch_history_ohlcv(symbol, start_date, end_date)
    except Exception as exc:
        return f"Error retrieving Futu stock data for {symbol}: {exc}"

    if data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    csv_string = data.set_index("Date").to_csv()
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Source: Futu OpenAPI\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + csv_string


def _load_indicator_ohlcv(symbol: str, curr_date: str) -> pd.DataFrame:
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_date_dt - relativedelta(years=5)).strftime("%Y-%m-%d")
    data = _fetch_history_ohlcv(symbol, start_date, curr_date)
    return data[data["Date"] <= pd.Timestamp(curr_date)]


def _get_indicator_values(
    symbol: str,
    indicator: str,
    curr_date: str,
) -> dict:
    data = _load_indicator_ohlcv(symbol, curr_date)
    if data.empty:
        return {}

    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df[indicator]

    values = {}
    for _, row in df.iterrows():
        value = row[indicator]
        values[row["Date"]] = "N/A" if pd.isna(value) else str(value)
    return values


def get_indicator(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    if indicator not in INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(INDICATOR_DESCRIPTIONS.keys())}"
        )

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_date_dt - relativedelta(days=look_back_days)

    try:
        indicator_values = _get_indicator_values(symbol, indicator, curr_date)
    except Exception as exc:
        return f"Error retrieving Futu indicator data for {symbol}: {exc}"

    ind_string = ""
    current_dt = curr_date_dt
    while current_dt >= start_dt:
        date_str = current_dt.strftime("%Y-%m-%d")
        value = indicator_values.get(date_str, "N/A: Not a trading day (weekend or holiday)")
        ind_string += f"{date_str}: {value}\n"
        current_dt -= relativedelta(days=1)

    return (
        f"## {indicator} values from {start_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + ind_string
        + "\n\n"
        + INDICATOR_DESCRIPTIONS[indicator]
    )
