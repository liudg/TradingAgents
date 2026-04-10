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

MARKET_PROXY_SYMBOLS = [
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "ARKK",
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


def get_market_monitor_universe() -> dict[str, list[str]]:
    return {
        "core_index_etfs": CORE_INDEX_ETFS.copy(),
        "sector_etfs": SECTOR_ETFS.copy(),
        "market_proxies": MARKET_PROXY_SYMBOLS.copy(),
        "all_symbols": sorted(
            set(CORE_INDEX_ETFS + SECTOR_ETFS + MARKET_PROXY_SYMBOLS + ["^VIX"])
        ),
    }
