CORE_INDEX_ETFS = [
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "ARKK",
    "TLT",
    "HYG",
    "GLD",
    "UUP",
]

SECTOR_ETFS = [
    "XLK",
    "XLY",
    "XLC",
    "XLI",
    "XLF",
    "XLV",
    "XLE",
    "XLB",
    "XLU",
    "XLP",
    "XLRE",
]

# Static Nasdaq 100 universe for the first implementation pass.
NASDAQ_100_TICKERS = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "AMAT", "AMD", "AMGN",
    "AMZN", "ANSS", "APP", "ARM", "ASML", "AVGO", "AXON", "AZN", "BIIB", "BKNG",
    "CDNS", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD", "CSCO", "CSGP", "CSX",
    "CTAS", "CTSH", "DASH", "DDOG", "DXCM", "EA", "EXC", "FANG", "FAST", "FTNT",
    "GEHC", "GFS", "GILD", "GOOG", "GOOGL", "HON", "IDXX", "INTC", "INTU", "ISRG",
    "KDP", "KHC", "KLAC", "LIN", "LRCX", "LULU", "MAR", "MCHP", "MDB", "MDLZ",
    "MELI", "META", "MNST", "MRVL", "MSFT", "MU", "NFLX", "NVDA", "NXPI", "ODFL",
    "ON", "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PYPL", "QCOM", "REGN",
    "ROP", "ROST", "SBUX", "SNPS", "TEAM", "TMUS", "TSLA", "TTD", "TTWO", "TXN",
    "VRSK", "VRTX", "WBD", "WDAY", "XEL", "ZS",
]


def get_market_monitor_universe() -> dict[str, list[str]]:
    return {
        "core_index_etfs": CORE_INDEX_ETFS.copy(),
        "sector_etfs": SECTOR_ETFS.copy(),
        "nasdaq_100": NASDAQ_100_TICKERS.copy(),
        "all_symbols": sorted(
            set(CORE_INDEX_ETFS + SECTOR_ETFS + NASDAQ_100_TICKERS + ["^VIX"])
        ),
    }
