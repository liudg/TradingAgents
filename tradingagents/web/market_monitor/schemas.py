from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


RunStatus = Literal["pending", "running", "completed", "failed"]
StageStatus = Literal["pending", "running", "completed", "failed", "skipped"]
SearchSlotKey = Literal[
    "macro_calendar",
    "earnings_watch",
    "policy_geopolitics",
    "risk_sentiment",
    "market_structure_optional",
]


class MarketMonitorRunCreateRequest(BaseModel):
    as_of_date: Optional[date] = None
    force_refresh: bool = False

    @field_validator("as_of_date")
    @classmethod
    def validate_as_of_date(cls, value: Optional[date]) -> Optional[date]:
        if value and value > date.today():
            raise ValueError("as_of_date 不能晚于今天")
        return value


class MarketMonitorRunCreateResponse(BaseModel):
    run_id: str
    status: RunStatus


class SearchEvidenceItem(BaseModel):
    slot_key: SearchSlotKey
    query: str | None = None
    title: str
    summary: str = ""
    source: str
    published_at: str | None = None
    captured_at: datetime | None = None


class MarketFactItem(BaseModel):
    fact_id: str
    statement: str
    source_type: Literal["local", "search"]
    confidence: float = Field(..., ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)


class MarketInputBundle(BaseModel):
    as_of_date: date
    generated_at: datetime
    local_market_data: dict[str, Any] = Field(default_factory=dict)
    derived_metrics: dict[str, Any] = Field(default_factory=dict)
    available_local_data: list[str] = Field(default_factory=list)
    open_gaps: list[str] = Field(default_factory=list)


class SearchSlotPack(BaseModel):
    slots: dict[str, list[SearchEvidenceItem]] = Field(default_factory=dict)


class MarketFactSheet(BaseModel):
    observed_facts: list[MarketFactItem] = Field(default_factory=list)
    filled_facts: list[MarketFactItem] = Field(default_factory=list)
    open_gaps: list[str] = Field(default_factory=list)
    evidence_index: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    fact_confidence: dict[str, float] = Field(default_factory=dict)


class JudgmentCard(BaseModel):
    label: str
    summary: str
    confidence: float = Field(..., ge=0, le=1)
    facts_used: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    action: str


class MarketJudgmentPack(BaseModel):
    long_term_card: JudgmentCard
    short_term_card: JudgmentCard
    system_risk_card: JudgmentCard
    event_risk_card: JudgmentCard
    panic_card: JudgmentCard


class ExecutionDecisionPack(BaseModel):
    summary: str
    confidence: float = Field(..., ge=0, le=1)
    decision_basis: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


class MarketMonitorRunResultSummary(BaseModel):
    long_term_label: str
    system_risk_label: str
    short_term_label: str
    event_risk_label: str
    panic_label: str
    execution_summary: str
    execution: ExecutionDecisionPack


class MarketMonitorRunDetail(BaseModel):
    run_id: str
    as_of_date: date
    status: RunStatus
    current_stage: str
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    result: MarketMonitorRunResultSummary | None = None


class MarketMonitorRunStageDetail(BaseModel):
    stage_key: str
    label: str
    status: StageStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)


class MarketMonitorRunStagesResponse(BaseModel):
    run_id: str
    stages: list[MarketMonitorRunStageDetail] = Field(default_factory=list)


class MarketMonitorRunEvidenceResponse(BaseModel):
    run_id: str
    evidence_index: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    search_slots: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    open_gaps: list[str] = Field(default_factory=list)


class MarketMonitorRunLogEntry(BaseModel):
    line_no: int
    timestamp: datetime | None = None
    level: str
    content: str


class MarketMonitorPromptSummary(BaseModel):
    prompt_id: str
    run_id: str
    stage_key: str
    attempt: int
    created_at: datetime
    model: str
    file_path: str | None = None


class MarketMonitorPromptDetail(MarketMonitorPromptSummary):
    payload: dict[str, Any] = Field(default_factory=dict)

