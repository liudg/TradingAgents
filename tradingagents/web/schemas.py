from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from cli.models import AnalystType
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
from tradingagents.llm_clients.validators import validate_model


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisJobRequest(BaseModel):
    ticker: str = Field(..., min_length=1, description="Ticker symbol, e.g. AAPL")
    trade_date: date
    selected_analysts: List[AnalystType] = Field(
        default_factory=lambda: [
            AnalystType.MARKET,
            AnalystType.SOCIAL,
            AnalystType.NEWS,
            AnalystType.FUNDAMENTALS,
        ]
    )
    llm_provider: str = DEFAULT_CONFIG["llm_provider"]
    deep_think_llm: str = DEFAULT_CONFIG["deep_think_llm"]
    quick_think_llm: str = DEFAULT_CONFIG["quick_think_llm"]
    backend_url: Optional[str] = DEFAULT_CONFIG["backend_url"]
    google_thinking_level: Optional[str] = DEFAULT_CONFIG["google_thinking_level"]
    openai_reasoning_effort: Optional[str] = DEFAULT_CONFIG["openai_reasoning_effort"]
    anthropic_effort: Optional[str] = DEFAULT_CONFIG["anthropic_effort"]
    output_language: str = DEFAULT_CONFIG["output_language"]
    max_debate_rounds: int = Field(
        DEFAULT_CONFIG["max_debate_rounds"], ge=1, le=10
    )
    max_risk_discuss_rounds: int = Field(
        DEFAULT_CONFIG["max_risk_discuss_rounds"], ge=1, le=10
    )
    max_recur_limit: int = Field(DEFAULT_CONFIG["max_recur_limit"], ge=1, le=300)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("trade_date")
    @classmethod
    def validate_trade_date(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("trade_date cannot be in the future")
        return value

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        provider = value.strip().lower()
        if provider not in MODEL_OPTIONS:
            raise ValueError(
                f"Unsupported llm_provider '{value}'. "
                f"Expected one of: {', '.join(sorted(MODEL_OPTIONS.keys()))}"
            )
        return provider

    def model_post_init(self, __context: Any) -> None:
        if not validate_model(self.llm_provider, self.deep_think_llm):
            raise ValueError(
                f"Unknown deep_think_llm '{self.deep_think_llm}' for provider "
                f"'{self.llm_provider}'"
            )
        if not validate_model(self.llm_provider, self.quick_think_llm):
            raise ValueError(
                f"Unknown quick_think_llm '{self.quick_think_llm}' for provider "
                f"'{self.llm_provider}'"
            )


class AnalysisJobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus


class AnalysisJobResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: int = Field(..., ge=0, le=100)
    request: AnalysisJobRequest
    final_state: Optional[Dict[str, Any]] = None
    decision: Optional[str] = None
    error_message: Optional[str] = None
    report_path: Optional[str] = None
    log_path: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class HistoricalReportItem(BaseModel):
    report_key: str
    title: str
    content: Optional[str] = None


class HistoricalReportAgentGroup(BaseModel):
    agent_key: str
    agent_name: str
    reports: List[HistoricalReportItem]


class HistoricalReportSummary(BaseModel):
    job_id: str
    ticker: str
    trade_date: date
    generated_at: datetime
    selected_analysts: List[str]
    llm_provider: str
    deep_think_llm: str
    quick_think_llm: str
    backend_url: Optional[str] = None
    google_thinking_level: Optional[str] = None
    openai_reasoning_effort: Optional[str] = None
    anthropic_effort: Optional[str] = None
    output_language: str
    max_debate_rounds: int
    max_risk_discuss_rounds: int
    max_recur_limit: int
    report_path: Optional[str] = None


class HistoricalReportDetail(HistoricalReportSummary):
    agent_reports: List[HistoricalReportAgentGroup]


class MetadataOptionsResponse(BaseModel):
    analysts: List[str]
    llm_providers: List[str]
    models: Dict[str, Dict[str, List[Dict[str, str]]]]
    default_config: Dict[str, Any]
