from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


AssessmentDataCompleteness = Literal["high", "medium", "low"]
MissingDataStatus = Literal["available", "missing", "filled_by_search", "not_applicable"]


class MarketMonitorSnapshotRequest(BaseModel):
    as_of_date: Optional[date] = None
    force_refresh: bool = False

    @field_validator("as_of_date")
    @classmethod
    def validate_as_of_date(cls, value: Optional[date]) -> Optional[date]:
        if value and value > date.today():
            raise ValueError("as_of_date 不能晚于今天")
        return value


class MarketMissingDataItem(BaseModel):
    key: str
    label: str
    required_for: list[str] = Field(default_factory=list)
    status: MissingDataStatus = "missing"
    note: str = ""


class MarketDataSnapshot(BaseModel):
    local_market_data: dict[str, Any] = Field(default_factory=dict)
    derived_metrics: dict[str, Any] = Field(default_factory=dict)
    llm_reasoning_notes: list[str] = Field(default_factory=list)


class MarketAssessmentCard(BaseModel):
    label: str
    summary: str
    confidence: float = Field(..., ge=0, le=1)
    data_completeness: AssessmentDataCompleteness
    key_evidence: list[str] = Field(default_factory=list)
    missing_data_filled_by_search: list[str] = Field(default_factory=list)
    action: str


class MarketAssessmentExecutionCard(MarketAssessmentCard):
    total_exposure_range: str
    new_position_allowed: bool
    chase_breakout_allowed: bool
    dip_buy_allowed: bool
    overnight_allowed: bool
    leverage_allowed: bool
    single_position_cap: str
    daily_risk_budget: str


class MarketAssessment(BaseModel):
    long_term_card: MarketAssessmentCard
    short_term_card: MarketAssessmentCard
    system_risk_card: MarketAssessmentCard
    execution_card: MarketAssessmentExecutionCard
    event_risk_card: MarketAssessmentCard
    panic_card: MarketAssessmentCard


class MarketMonitorSnapshotResponse(BaseModel):
    timestamp: datetime
    as_of_date: date
    trace_id: Optional[str] = None
    market_data_snapshot: MarketDataSnapshot
    missing_data: list[MarketMissingDataItem] = Field(default_factory=list)
    assessment: MarketAssessment
    evidence_sources: list[str] = Field(default_factory=list)
    overall_confidence: float = Field(..., ge=0, le=1)


class MarketHistoryPoint(BaseModel):
    trade_date: date
    long_term_label: str
    short_term_label: str
    system_risk_label: str
    execution_label: str
    overall_confidence: float = Field(..., ge=0, le=1)


class MarketMonitorHistoryResponse(BaseModel):
    as_of_date: date
    points: list[MarketHistoryPoint] = Field(default_factory=list)


class MarketMonitorDataStatusResponse(BaseModel):
    as_of_date: date
    available_local_data: list[str] = Field(default_factory=list)
    missing_data: list[MarketMissingDataItem] = Field(default_factory=list)
    search_enabled: bool = True
    latest_cache_status: dict[str, Any] = Field(default_factory=dict)


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
    overall_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    long_term_label: Optional[str] = None
    execution_label: Optional[str] = None


class MarketMonitorTraceDetail(MarketMonitorTraceSummary):
    request: dict[str, Any] = Field(default_factory=dict)
    cache_decision: dict[str, Any] = Field(default_factory=dict)
    dataset_summary: dict[str, Any] = Field(default_factory=dict)
    context_summary: dict[str, Any] = Field(default_factory=dict)
    assessment_summary: dict[str, Any] = Field(default_factory=dict)
    response_summary: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)
