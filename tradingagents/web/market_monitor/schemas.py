from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from tradingagents.web.schemas import JobStatus


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
MarketMonitorRunMode = Literal["snapshot", "history", "data_status", "debug_card"]
MarketMonitorStageStatus = Literal["pending", "running", "completed", "failed", "skipped"]
MarketMonitorConfidence = Literal["low", "medium", "high"]
MarketMonitorDebugCardType = Literal[
    "long_term",
    "short_term",
    "system_risk",
    "style",
    "event_risk",
    "panic",
    "execution",
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


class MarketMonitorRunDebugOptions(BaseModel):
    debug_card: MarketMonitorDebugCardType | None = None
    reuse_fact_sheet: bool = False
    replay_from_run_id: str | None = None

    @model_validator(mode="after")
    def validate_replay_requirements(self) -> "MarketMonitorRunDebugOptions":
        if self.reuse_fact_sheet and not self.replay_from_run_id:
            raise ValueError("reuse_fact_sheet=true 时必须提供 replay_from_run_id")
        return self


class MarketMonitorRunLlmConfig(BaseModel):
    provider: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None


class MarketMonitorRunRequest(BaseModel):
    trigger_endpoint: Literal["snapshot", "history", "data_status", "debug_card"]
    as_of_date: date | None = None
    days: int | None = Field(default=None, ge=1, le=60)
    force_refresh: bool = False
    mode: MarketMonitorRunMode | None = None
    debug_options: MarketMonitorRunDebugOptions | None = None
    llm_config: MarketMonitorRunLlmConfig | None = None

    @field_validator("as_of_date")
    @classmethod
    def validate_as_of_date(cls, value: date | None) -> date | None:
        if value and value > date.today():
            raise ValueError("as_of_date 不能晚于今天")
        return value

    @model_validator(mode="after")
    def validate_debug_options(self) -> "MarketMonitorRunRequest":
        if self.trigger_endpoint == "debug_card":
            if self.debug_options is None or self.debug_options.debug_card is None:
                raise ValueError("debug_card 运行缺少 debug_options.debug_card")
        return self


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


class MarketMonitorEvidenceRef(BaseModel):
    source_type: str
    source_label: str
    snippet: str | None = None
    timestamp: datetime | None = None
    confidence: MarketMonitorConfidence | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketMonitorReasoningFields(BaseModel):
    reasoning_summary: str | None = None
    key_drivers: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    evidence_refs: list[MarketMonitorEvidenceRef] = Field(default_factory=list)
    confidence: MarketMonitorConfidence | None = None


class MarketMonitorLayerMetric(BaseModel):
    score: float = Field(..., ge=0, le=100)
    delta_5d: float
    valid: bool | None = None
    preferred: bool | None = None


class MarketMonitorScoreCard(MarketMonitorReasoningFields):
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


class MarketMonitorStyleEffectiveness(MarketMonitorReasoningFields):
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


class MarketMonitorEventRiskFlag(MarketMonitorReasoningFields):
    index_level: MarketMonitorIndexEventRisk = Field(default_factory=MarketMonitorIndexEventRisk)
    stock_level: MarketMonitorStockEventRisk = Field(default_factory=MarketMonitorStockEventRisk)


class MarketMonitorSignalConfirmation(BaseModel):
    current_regime_observations: int
    risk_loosening_unlock_in_observations: int
    note: str


class MarketMonitorExecutionCard(MarketMonitorReasoningFields):
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


class MarketMonitorPanicCard(MarketMonitorReasoningFields):
    score: float = Field(..., ge=0, le=100)
    zone: str
    state: str
    panic_extreme_score: float = Field(..., ge=0, le=100)
    selling_exhaustion_score: float = Field(..., ge=0, le=100)
    intraday_reversal_score: float = Field(..., ge=0, le=100)
    action: str
    system_risk_override: str | None = None
    stop_loss: str
    profit_rule: str
    timeout_warning: bool
    refreshes_held: int
    early_entry_allowed: bool
    max_position_hint: str


class MarketMonitorSourceCoverage(BaseModel):
    completeness: Literal["high", "medium", "low"]
    available_sources: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    degraded: bool = False


class MarketMonitorFactSheet(BaseModel):
    as_of_date: date
    generated_at: datetime
    local_facts: dict[str, Any] = Field(default_factory=dict)
    derived_metrics: dict[str, Any] = Field(default_factory=dict)
    search_facts: list[dict[str, Any]] = Field(default_factory=list)
    open_gaps: list[str] = Field(default_factory=list)
    source_coverage: MarketMonitorSourceCoverage | None = None
    evidence_refs: list[MarketMonitorEvidenceRef] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MarketMonitorPromptTrace(BaseModel):
    stage: str
    card_type: str | None = None
    model: str | None = None
    provider: str | None = None
    input_summary: str | None = None
    prompt_text: str | None = None
    raw_response: str | None = None
    parsed_ok: bool = False
    latency_ms: int | None = None
    token_usage: dict[str, int] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class MarketMonitorDebugCardResponse(BaseModel):
    card_type: MarketMonitorDebugCardType
    as_of_date: date
    fact_sheet_reused: bool = False
    fact_sheet_source_run_id: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    prompt_traces: list[MarketMonitorPromptTrace] = Field(default_factory=list)


class MarketMonitorStageResult(BaseModel):
    stage_name: str
    status: MarketMonitorStageStatus = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    artifact_path: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketMonitorRunManifest(BaseModel):
    run_id: str
    mode: MarketMonitorRunMode
    request: MarketMonitorRunRequest
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    results_dir: str
    log_path: str
    error_message: str | None = None
    recoverable: bool = False
    llm_config: MarketMonitorRunLlmConfig | None = None
    debug_options: MarketMonitorRunDebugOptions | None = None
    stage_results: list[MarketMonitorStageResult] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    prompt_trace_count: int = 0


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
    fact_sheet: MarketMonitorFactSheet | None = None
    prompt_traces: list[MarketMonitorPromptTrace] = Field(default_factory=list)
    run_id: str | None = None


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
    run_id: str | None = None


class MarketMonitorDataStatusResponse(BaseModel):
    timestamp: datetime
    as_of_date: date
    source_coverage: MarketMonitorSourceCoverage
    degraded_factors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    open_gaps: list[str] = Field(default_factory=list)
    fact_sheet: MarketMonitorFactSheet | None = None
    run_id: str | None = None


class HistoricalMarketMonitorRunSummary(BaseModel):
    run_id: str
    trigger_endpoint: Literal["snapshot", "history", "data_status", "debug_card"]
    as_of_date: date
    days: int | None = None
    status: JobStatus
    generated_at: datetime
    data_freshness: str | None = None
    source_completeness: Literal["high", "medium", "low"] | None = None
    regime_label: str | None = None
    degraded: bool = False
    recoverable: bool = False
    error_message: str | None = None
    log_path: str | None = None
    results_dir: str | None = None


class HistoricalMarketMonitorRunDetail(HistoricalMarketMonitorRunSummary):
    request: MarketMonitorRunRequest
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    snapshot: MarketMonitorSnapshotResponse | None = None
    history: MarketMonitorHistoryResponse | None = None
    data_status: MarketMonitorDataStatusResponse | None = None
    debug_card: MarketMonitorDebugCardResponse | None = None
    fact_sheet: MarketMonitorFactSheet | None = None
    manifest: MarketMonitorRunManifest | None = None
    stage_results: list[MarketMonitorStageResult] = Field(default_factory=list)
    prompt_traces: list[MarketMonitorPromptTrace] = Field(default_factory=list)
