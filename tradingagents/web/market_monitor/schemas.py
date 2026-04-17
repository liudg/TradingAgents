from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


MarketMonitorSymbolCacheReadState = Literal[
    "cache_missing",
    "cache_corrupted",
    "cache_invalid_structure",
    "cache_stale",
    "cache_hit",
]
MarketMonitorSymbolCacheState = Literal[
    "cache_missing",
    "cache_corrupted",
    "cache_invalid_structure",
    "cache_stale",
    "cache_hit",
    "refreshed",
    "stale_fallback",
    "empty",
]


class MarketMonitorSymbolCacheMetadata(BaseModel):
    schema_version: int = 1
    cache_kind: Literal["symbol_daily_history"] = "symbol_daily_history"
    symbol: str
    safe_symbol: str
    created_at: datetime
    updated_at: datetime
    last_successful_refresh_at: datetime
    last_successful_as_of_date: date
    expected_close_date: date
    date_range_start: date | None = None
    date_range_end: date | None = None
    trading_days: int = Field(..., ge=0)
    columns: list[str] = Field(default_factory=list)
    source: str = "yfinance"
    source_params: dict[str, Any] = Field(default_factory=dict)
    max_staleness_days: int = Field(default=3, ge=0)
    retention_expires_on: date | None = None
    content_hash: str | None = None


class MarketMonitorSymbolCacheReadResult(BaseModel):
    state: MarketMonitorSymbolCacheReadState
    symbol: str
    safe_symbol: str
    frame: Any = None
    metadata: MarketMonitorSymbolCacheMetadata | None = None
    reason: str | None = None
    cache_end_date: date | None = None
    last_successful_refresh_at: datetime | None = None


class MarketMonitorSnapshotRequest(BaseModel):
    as_of_date: date | None = None
    force_refresh: bool = False

    @field_validator("as_of_date")
    @classmethod
    def validate_as_of_date(cls, value: date | None) -> date | None:
        if value and value > date.today():
            raise ValueError("as_of_date 不能晚于今天")
        return value


class MarketMonitorHistoryRequest(BaseModel):
    as_of_date: date | None = None
    days: int = Field(default=20, ge=1, le=60)
    force_refresh: bool = False

    @field_validator("as_of_date")
    @classmethod
    def validate_as_of_date(cls, value: date | None) -> date | None:
        if value and value > date.today():
            raise ValueError("as_of_date 不能晚于今天")
        return value


class MarketMonitorLayerMetric(BaseModel):
    score: float = Field(..., ge=0, le=100)
    delta_5d: float
    valid: bool | None = None
    preferred: bool | None = None


class MarketMonitorScoreCard(BaseModel):
    score: float = Field(..., ge=0, le=100)
    zone: str
    delta_1d: float
    delta_5d: float
    slope_state: str
    summary: str
    action: str
    recommended_exposure: str | None = None


class MarketMonitorSystemRiskCard(MarketMonitorScoreCard):
    liquidity_stress_score: float = Field(..., ge=0, le=100)
    risk_appetite_score: float = Field(..., ge=0, le=100)
    pcr_percentile: float | None = None
    pcr_absolute: float | None = None
    pcr_panic_flag: bool | None = None


class MarketMonitorStyleTacticLayer(BaseModel):
    trend_breakout: MarketMonitorLayerMetric
    dip_buy: MarketMonitorLayerMetric
    oversold_bounce: MarketMonitorLayerMetric
    top_tactic: str
    avoid_tactic: str


class MarketMonitorStyleAssetLayer(BaseModel):
    large_cap_tech: MarketMonitorLayerMetric
    small_cap_momentum: MarketMonitorLayerMetric
    defensive: MarketMonitorLayerMetric
    energy_cyclical: MarketMonitorLayerMetric
    financials: MarketMonitorLayerMetric
    preferred_assets: list[str] = Field(default_factory=list)
    avoid_assets: list[str] = Field(default_factory=list)


class MarketMonitorStyleEffectiveness(BaseModel):
    tactic_layer: MarketMonitorStyleTacticLayer
    asset_layer: MarketMonitorStyleAssetLayer


class MarketMonitorActionModifier(BaseModel):
    new_position_allowed: bool | None = None
    overnight_allowed: bool | None = None
    single_position_cap_multiplier: float | None = None
    note: str | None = None


class MarketMonitorIndexEventRisk(BaseModel):
    active: bool = False
    type: str | None = None
    days_to_event: int | None = None
    action_modifier: MarketMonitorActionModifier | None = None


class MarketMonitorStockEventRisk(BaseModel):
    earnings_stocks: list[str] = Field(default_factory=list)
    rule: str | None = None


class MarketMonitorEventRiskFlag(BaseModel):
    index_level: MarketMonitorIndexEventRisk = Field(default_factory=MarketMonitorIndexEventRisk)
    stock_level: MarketMonitorStockEventRisk = Field(default_factory=MarketMonitorStockEventRisk)


class MarketMonitorSignalConfirmation(BaseModel):
    current_regime_days: int
    downgrade_unlock_in_days: int
    note: str


class MarketMonitorExecutionCard(BaseModel):
    regime_label: str
    conflict_mode: str
    total_exposure_range: str
    new_position_allowed: bool
    chase_breakout_allowed: bool
    dip_buy_allowed: bool
    overnight_allowed: bool
    leverage_allowed: bool
    single_position_cap: str
    daily_risk_budget: str
    tactic_preference: str
    preferred_assets: list[str] = Field(default_factory=list)
    avoid_assets: list[str] = Field(default_factory=list)
    signal_confirmation: MarketMonitorSignalConfirmation
    event_risk_flag: MarketMonitorEventRiskFlag
    summary: str


class MarketMonitorPanicCard(BaseModel):
    score: float = Field(..., ge=0, le=100)
    zone: str
    state: str
    panic_extreme_score: float = Field(..., ge=0, le=100)
    selling_exhaustion_score: float = Field(..., ge=0, le=100)
    reversal_confirmation_score: float = Field(..., ge=0, le=100)
    action: str
    system_risk_override: str | None = None
    stop_loss: str
    profit_rule: str
    timeout_warning: bool
    days_held: int
    early_entry_allowed: bool
    max_position_hint: str


class MarketMonitorSourceCoverage(BaseModel):
    completeness: Literal["high", "medium", "low"]
    available_sources: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    degraded: bool = False


class MarketMonitorSnapshotResponse(BaseModel):
    timestamp: datetime
    as_of_date: date
    data_freshness: str
    long_term_score: MarketMonitorScoreCard
    short_term_score: MarketMonitorScoreCard
    system_risk_score: MarketMonitorSystemRiskCard
    style_effectiveness: MarketMonitorStyleEffectiveness
    execution_card: MarketMonitorExecutionCard
    panic_reversal_score: MarketMonitorPanicCard
    event_risk_flag: MarketMonitorEventRiskFlag
    source_coverage: MarketMonitorSourceCoverage
    degraded_factors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MarketMonitorHistoryPoint(BaseModel):
    trade_date: date
    long_term_score: float = Field(..., ge=0, le=100)
    short_term_score: float = Field(..., ge=0, le=100)
    system_risk_score: float = Field(..., ge=0, le=100)
    panic_score: float = Field(..., ge=0, le=100)
    regime_label: str


class MarketMonitorHistoryResponse(BaseModel):
    as_of_date: date
    points: list[MarketMonitorHistoryPoint] = Field(default_factory=list)


class MarketMonitorDataStatusResponse(BaseModel):
    timestamp: datetime
    as_of_date: date
    source_coverage: MarketMonitorSourceCoverage
    degraded_factors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    open_gaps: list[str] = Field(default_factory=list)
