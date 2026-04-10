import os

import yfinance as _yf


def configure_yfinance_proxy() -> None:
    proxy_url = os.getenv("YFINANCE_PROXY", "").strip()
    http_proxy = os.getenv("YFINANCE_HTTP_PROXY", "").strip()
    https_proxy = os.getenv("YFINANCE_HTTPS_PROXY", "").strip()

    if proxy_url:
        _yf.config.network.proxy = {
            "http": proxy_url,
            "https": proxy_url,
        }
        return

    if http_proxy or https_proxy:
        _yf.config.network.proxy = {
            "http": http_proxy or https_proxy,
            "https": https_proxy or http_proxy,
        }
        return

    _yf.config.network.proxy = None


def get_yf():
    configure_yfinance_proxy()
    return _yf
