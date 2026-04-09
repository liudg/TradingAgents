from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


MarketRegimeLabel = Literal["绿灯", "黄灯", "黄绿灯-Swing", "橙灯", "红灯"]
PanicState = Literal["无信号", "panic_watch", "panic_confirmed"]
CoverageStatus = Literal["full", "partial", "degraded"]


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
    preferred_assets: List[str] = Field(default_factory=list)
    avoid_assets: List[str] = Field(default_factory=list)


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
    earnings_stocks: List[str] = Field(default_factory=list)
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
    preferred_assets: List[str] = Field(default_factory=list)
    avoid_assets: List[str] = Field(default_factory=list)
    signal_confirmation: MarketExecutionSignalConfirmation
    event_risk_flag: MarketEventRiskFlag


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
    degraded_factors: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class MarketMonitorSnapshotResponse(BaseModel):
    timestamp: datetime
    as_of_date: date
    long_term_score: MarketScoreCard
    short_term_score: MarketScoreCard
    system_risk_score: MarketScoreCard
    style_effectiveness: MarketStyleEffectiveness
    execution_card: MarketExecutionCard
    panic_reversal_score: MarketPanicReversalCard
    event_risk_flag: MarketEventRiskFlag
    source_coverage: MarketSourceCoverage


class MarketHistoryPoint(BaseModel):
    trade_date: date
    regime_label: MarketRegimeLabel
    long_term_score: float
    short_term_score: float
    system_risk_score: float
    panic_reversal_score: float


class MarketMonitorHistoryResponse(BaseModel):
    as_of_date: date
    points: List[MarketHistoryPoint] = Field(default_factory=list)


class MarketMonitorDataStatusResponse(BaseModel):
    as_of_date: date
    source_coverage: MarketSourceCoverage
    available_sources: List[str] = Field(default_factory=list)
    pending_sources: List[str] = Field(default_factory=list)
