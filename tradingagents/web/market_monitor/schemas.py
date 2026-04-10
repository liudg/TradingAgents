from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


MarketRegimeLabel = Literal[
    "green",
    "yellow",
    "yellow_green_swing",
    "orange",
    "red",
]
PanicState = Literal["none", "watch", "confirmed"]
CoverageStatus = Literal["full", "partial", "degraded"]
OverlayStatus = Literal["skipped", "applied", "error"]


class MarketMonitorSnapshotRequest(BaseModel):
    as_of_date: Optional[date] = None
    force_refresh: bool = False

    @field_validator("as_of_date")
    @classmethod
    def validate_as_of_date(cls, value: Optional[date]) -> Optional[date]:
        if value and value > date.today():
            raise ValueError("as_of_date cannot be in the future")
        return value


class MarketScoreCard(BaseModel):
    score: float = Field(..., ge=0, le=100)
    zone: str
    delta_1d: float
    delta_5d: float
    slope_state: str
    action: str


class MarketStyleSignal(BaseModel):
    score: float = Field(..., ge=0, le=100)
    preferred: Optional[bool] = None
    valid: Optional[bool] = None
    delta_5d: float


class MarketStyleTacticLayer(BaseModel):
    trend_breakout: MarketStyleSignal
    dip_buy: MarketStyleSignal
    oversold_bounce: MarketStyleSignal
    top_tactic: str
    avoid_tactic: str


class MarketStyleAssetLayer(BaseModel):
    large_cap_tech: MarketStyleSignal
    small_cap_momentum: MarketStyleSignal
    defensive: MarketStyleSignal
    energy_cyclical: MarketStyleSignal
    financials: MarketStyleSignal
    preferred_assets: list[str] = Field(default_factory=list)
    avoid_assets: list[str] = Field(default_factory=list)


class MarketStyleEffectiveness(BaseModel):
    tactic_layer: MarketStyleTacticLayer
    asset_layer: MarketStyleAssetLayer


class MarketEventRiskModifier(BaseModel):
    new_position_allowed: Optional[bool] = None
    overnight_allowed: Optional[bool] = None
    single_position_cap_multiplier: Optional[float] = None
    note: Optional[str] = None


class MarketIndexEventRisk(BaseModel):
    active: bool = False
    type: Optional[str] = None
    days_to_event: Optional[int] = None
    action_modifier: Optional[MarketEventRiskModifier] = None


class MarketStockEventRisk(BaseModel):
    earnings_stocks: list[str] = Field(default_factory=list)
    rule: Optional[str] = None


class MarketEventRiskFlag(BaseModel):
    index_level: MarketIndexEventRisk
    stock_level: MarketStockEventRisk


class MarketExecutionSignalConfirmation(BaseModel):
    current_regime_days: int
    downgrade_unlock_in_days: int
    note: str


class MarketExecutionCard(BaseModel):
    regime_label: MarketRegimeLabel
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
    signal_confirmation: MarketExecutionSignalConfirmation
    event_risk_flag: MarketEventRiskFlag
    summary: str = ""


class MarketPanicReversalCard(BaseModel):
    score: float = Field(..., ge=0, le=100)
    zone: str
    state: PanicState
    panic_extreme_score: float = Field(..., ge=0, le=100)
    selling_exhaustion_score: float = Field(..., ge=0, le=100)
    intraday_reversal_score: float = Field(..., ge=0, le=100)
    followthrough_confirmation_score: float = Field(..., ge=0, le=100)
    action: str
    system_risk_override: Optional[str] = None
    stop_loss: str
    profit_rule: str
    timeout_warning: bool = False
    days_held: int = 0
    early_entry_allowed: bool = False


class MarketSourceCoverage(BaseModel):
    status: CoverageStatus
    data_freshness: str
    degraded_factors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MarketMonitorRuleSnapshot(BaseModel):
    ready: bool
    long_term_score: Optional[MarketScoreCard] = None
    short_term_score: Optional[MarketScoreCard] = None
    system_risk_score: Optional[MarketScoreCard] = None
    style_effectiveness: Optional[MarketStyleEffectiveness] = None
    panic_reversal_score: Optional[MarketPanicReversalCard] = None
    base_regime_label: Optional[MarketRegimeLabel] = None
    base_execution_card: Optional[MarketExecutionCard] = None
    base_event_risk_flag: MarketEventRiskFlag
    source_coverage: MarketSourceCoverage
    missing_inputs: list[str] = Field(default_factory=list)
    degraded_factors: list[str] = Field(default_factory=list)
    key_indicators: dict[str, Any] = Field(default_factory=dict)


class MarketExecutionAdjustments(BaseModel):
    regime_label: Optional[MarketRegimeLabel] = None
    conflict_mode: Optional[str] = None
    new_position_allowed: Optional[bool] = None
    chase_breakout_allowed: Optional[bool] = None
    dip_buy_allowed: Optional[bool] = None
    overnight_allowed: Optional[bool] = None
    daily_risk_budget: Optional[str] = None
    summary: Optional[str] = None


class MarketMonitorModelOverlay(BaseModel):
    status: OverlayStatus
    regime_override: Optional[MarketRegimeLabel] = None
    execution_adjustments: Optional[MarketExecutionAdjustments] = None
    event_risk_override: Optional[MarketEventRiskFlag] = None
    market_narrative: str = ""
    risk_narrative: str = ""
    panic_narrative: str = ""
    evidence_sources: list[str] = Field(default_factory=list)
    model_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    notes: list[str] = Field(default_factory=list)


class MarketMonitorSnapshotResponse(BaseModel):
    timestamp: datetime
    as_of_date: date
    trace_id: Optional[str] = None
    rule_snapshot: MarketMonitorRuleSnapshot
    model_overlay: MarketMonitorModelOverlay
    final_execution_card: Optional[MarketExecutionCard] = None


class MarketHistoryPoint(BaseModel):
    trade_date: date
    regime_label: MarketRegimeLabel
    long_term_score: float
    short_term_score: float
    system_risk_score: float
    panic_reversal_score: float


class MarketMonitorHistoryResponse(BaseModel):
    as_of_date: date
    points: list[MarketHistoryPoint] = Field(default_factory=list)


class MarketMonitorDataStatusResponse(BaseModel):
    as_of_date: date
    source_coverage: MarketSourceCoverage
    available_sources: list[str] = Field(default_factory=list)
    pending_sources: list[str] = Field(default_factory=list)


class MarketMonitorTraceLogEntry(BaseModel):
    line_no: int
    timestamp: Optional[datetime] = None
    level: str
    content: str


class MarketMonitorTraceSummary(BaseModel):
    trace_id: str
    as_of_date: date
    status: str
    force_refresh: bool = False
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    rule_ready: Optional[bool] = None
    base_regime_label: Optional[MarketRegimeLabel] = None
    final_regime_label: Optional[MarketRegimeLabel] = None
    overlay_status: Optional[OverlayStatus] = None


class MarketMonitorTraceDetail(MarketMonitorTraceSummary):
    request: dict[str, Any] = Field(default_factory=dict)
    cache_decision: dict[str, Any] = Field(default_factory=dict)
    dataset_summary: dict[str, Any] = Field(default_factory=dict)
    rule_snapshot_summary: dict[str, Any] = Field(default_factory=dict)
    overlay_summary: dict[str, Any] = Field(default_factory=dict)
    final_execution_summary: dict[str, Any] = Field(default_factory=dict)
    response_summary: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)
