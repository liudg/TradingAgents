BROAD_INDEX_ETFS = [
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
]

CREDIT_PROXY_ETFS = [
    "LQD",
    "JNK",
]

HIGH_BETA_PROXY_SYMBOLS = [
    "ARKK",
    "IWM",
]

CORE_INDEX_ETFS = [
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "LQD",
    "JNK",
    "ARKK",
]

SECTOR_ETFS = [
    "XLB",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
    "XLRE",
    "XLC",
]

BREADTH_PROXY_SYMBOLS = BROAD_INDEX_ETFS + SECTOR_ETFS

MARKET_PROXY_SYMBOLS = list(
    dict.fromkeys(BREADTH_PROXY_SYMBOLS + CREDIT_PROXY_ETFS + HIGH_BETA_PROXY_SYMBOLS)
)


def get_market_monitor_universe() -> dict[str, list[str]]:
    return {
        "broad_index_etfs": BROAD_INDEX_ETFS.copy(),
        "credit_proxy_etfs": CREDIT_PROXY_ETFS.copy(),
        "high_beta_proxy_symbols": HIGH_BETA_PROXY_SYMBOLS.copy(),
        "core_index_etfs": CORE_INDEX_ETFS.copy(),
        "sector_etfs": SECTOR_ETFS.copy(),
        "breadth_proxy_symbols": BREADTH_PROXY_SYMBOLS.copy(),
        "market_proxies": MARKET_PROXY_SYMBOLS.copy(),
        "all_symbols": sorted(set(CORE_INDEX_ETFS + SECTOR_ETFS + ["^VIX"])),
    }
