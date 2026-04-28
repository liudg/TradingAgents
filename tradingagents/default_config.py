import os

_TRADINGAGENTS_HOME = os.path.join(os.path.expanduser("~"), ".tradingagents")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", os.path.join(_TRADINGAGENTS_HOME, "logs")),
    "data_cache_dir": os.getenv("TRADINGAGENTS_CACHE_DIR", os.path.join(_TRADINGAGENTS_HOME, "cache")),
    "memory_dir": os.getenv("TRADINGAGENTS_MEMORY_DIR", os.path.join(_TRADINGAGENTS_HOME, "memory")),
    # LLM settings
    "llm_provider": "codex",
    "deep_think_llm": "gpt-5.5",
    "quick_think_llm": "gpt-5.4-mini",
    "backend_url": "http://127.0.0.1:8317/v1",
    "market_monitor_symbol_cache_max_age_days": 3,
    "market_monitor_symbol_cache_retention_days": 30,
    "market_monitor_symbol_cache_cleanup_interval_seconds": 3600,
    "market_monitor_run_retention_days": 30,
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    "codex_reasoning_effort": None,     # "medium", "high", "low"
    "anthropic_effort": None,           # "high", "medium", "low"
    # Output language for analyst reports and final decision
    # Internal agent debate stays in English for reasoning quality
    "output_language": "Chinese",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Data vendor configuration
    # Category-level configuration (default for all tools in category)
    "data_vendors": {
        "core_stock_apis": "yfinance",       # Options: alpha_vantage, futu, yfinance
        "technical_indicators": "yfinance",  # Options: alpha_vantage, futu, yfinance
        "fundamental_data": "alpha_vantage",      # Options: alpha_vantage, yfinance
        "news_data": "alpha_vantage",             # Options: alpha_vantage, yfinance
    },
    # Futu OpenD settings
    "futu_opend_host": "127.0.0.1",
    "futu_opend_port": 11111,
    # Tool-level configuration (takes precedence over category-level)
    "tool_vendors": {
        # Example: "get_stock_data": "alpha_vantage",  # Override category default
    },
}
