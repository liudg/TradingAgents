import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from datetime import date

from cli.models import AnalystType
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.web.backtest.manager import BacktestJobManager
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
from tradingagents.web.analysis.manager import AnalysisJobManager
from tradingagents.web.schemas import (
    AnalysisJobCreateResponse,
    AnalysisJobLogEntry,
    AnalysisJobRequest,
    AnalysisJobResponse,
    BacktestJobCreateResponse,
    BacktestJobRequest,
    BacktestJobResponse,
    HistoricalBacktestDetail,
    HistoricalBacktestSummary,
    HistoricalReportDetail,
    HistoricalReportSummary,
    MetadataOptionsResponse,
)
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorDataStatusResponse,
    MarketMonitorHistoryResponse,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
    MarketMonitorTraceDetail,
    MarketMonitorTraceLogEntry,
    MarketMonitorTraceSummary,
)
from tradingagents.web.market_monitor.service import MarketMonitorService


load_dotenv()

app = FastAPI(
    title="TradingAgents Web API",
    description="Async HTTP API wrapper for TradingAgents analysis jobs.",
    version="0.2.3",
)
job_manager = AnalysisJobManager()
backtest_manager = BacktestJobManager()
market_monitor_service = MarketMonitorService()


@app.post("/api/analysis-jobs", response_model=AnalysisJobCreateResponse)
def create_analysis_job(request: AnalysisJobRequest) -> AnalysisJobCreateResponse:
    return job_manager.create_job(request)


@app.get("/api/analysis-jobs/{job_id}", response_model=AnalysisJobResponse)
def get_analysis_job(job_id: str) -> AnalysisJobResponse:
    try:
        return job_manager.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Analysis job not found") from exc


@app.get("/api/analysis-jobs/{job_id}/report")
def get_analysis_report(job_id: str) -> FileResponse:
    try:
        report_path = job_manager.get_report_path(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Analysis job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")

    return FileResponse(
        path=report_path,
        media_type="text/markdown; charset=utf-8",
        filename=report_path.name,
    )


@app.get(
    "/api/analysis-jobs/{job_id}/logs",
    response_model=list[AnalysisJobLogEntry],
)
def get_analysis_job_logs(job_id: str) -> list[AnalysisJobLogEntry]:
    try:
        return job_manager.list_job_logs(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Analysis job not found") from exc


@app.get("/api/historical-reports", response_model=list[HistoricalReportSummary])
def list_historical_reports() -> list[HistoricalReportSummary]:
    return job_manager.list_historical_reports()


@app.get(
    "/api/historical-reports/{job_id}",
    response_model=HistoricalReportDetail,
)
def get_historical_report(job_id: str) -> HistoricalReportDetail:
    try:
        return job_manager.get_historical_report(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Historical report not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/metadata/options", response_model=MetadataOptionsResponse)
def get_metadata_options() -> MetadataOptionsResponse:
    default_config = DEFAULT_CONFIG.copy()
    default_config.pop("max_recur_limit", None)
    return MetadataOptionsResponse(
        analysts=[item.value for item in AnalystType],
        llm_providers=sorted(MODEL_OPTIONS.keys()),
        models={
            provider: {
                mode: [
                    {
                        "label": label,
                        "value": value,
                    }
                    for label, value in model_options
                ]
                for mode, model_options in mode_options.items()
            }
            for provider, mode_options in MODEL_OPTIONS.items()
        },
        default_config=default_config,
    )


@app.post("/api/backtest-jobs", response_model=BacktestJobCreateResponse)
def create_backtest_job(request: BacktestJobRequest) -> BacktestJobCreateResponse:
    return backtest_manager.create_job(request)


@app.get("/api/backtest-jobs/{job_id}", response_model=BacktestJobResponse)
def get_backtest_job(job_id: str) -> BacktestJobResponse:
    try:
        return backtest_manager.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Backtest job not found") from exc


@app.get("/api/backtest-jobs/{job_id}/logs", response_model=list[AnalysisJobLogEntry])
def get_backtest_job_logs(job_id: str) -> list[AnalysisJobLogEntry]:
    try:
        return backtest_manager.list_job_logs(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Backtest job not found") from exc


@app.get("/api/historical-backtests", response_model=list[HistoricalBacktestSummary])
def list_historical_backtests() -> list[HistoricalBacktestSummary]:
    return backtest_manager.list_historical_backtests()


@app.get("/api/historical-backtests/{job_id}", response_model=HistoricalBacktestDetail)
def get_historical_backtest(job_id: str) -> HistoricalBacktestDetail:
    try:
        return backtest_manager.get_historical_backtest(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Historical backtest not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/market-monitor/snapshot", response_model=MarketMonitorSnapshotResponse)
def get_market_monitor_snapshot(as_of_date: str | None = None) -> MarketMonitorSnapshotResponse:
    request = MarketMonitorSnapshotRequest(
        as_of_date=as_of_date,
    )
    return market_monitor_service.get_snapshot(request)


@app.post("/api/market-monitor/snapshot", response_model=MarketMonitorSnapshotResponse)
def create_market_monitor_snapshot(
    request: MarketMonitorSnapshotRequest,
) -> MarketMonitorSnapshotResponse:
    return market_monitor_service.get_snapshot(request)


@app.get("/api/market-monitor/history", response_model=MarketMonitorHistoryResponse)
def get_market_monitor_history(
    as_of_date: str | None = None, days: int = 10
) -> MarketMonitorHistoryResponse:
    request = MarketMonitorSnapshotRequest(as_of_date=as_of_date)
    target_date = request.as_of_date or date.today()
    return market_monitor_service.get_history(target_date, days)


@app.get(
    "/api/market-monitor/data-status",
    response_model=MarketMonitorDataStatusResponse,
)
def get_market_monitor_data_status(
    as_of_date: str | None = None,
) -> MarketMonitorDataStatusResponse:
    request = MarketMonitorSnapshotRequest(as_of_date=as_of_date)
    target_date = request.as_of_date or date.today()
    return market_monitor_service.get_data_status(target_date)


@app.get(
    "/api/market-monitor/traces",
    response_model=list[MarketMonitorTraceSummary],
)
def list_market_monitor_traces(
    as_of_date: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> list[MarketMonitorTraceSummary]:
    request = MarketMonitorSnapshotRequest(as_of_date=as_of_date)
    target_date = request.as_of_date
    return market_monitor_service.list_traces(as_of_date=target_date, status=status, limit=limit)


@app.get(
    "/api/market-monitor/traces/{trace_id}",
    response_model=MarketMonitorTraceDetail,
)
def get_market_monitor_trace(trace_id: str) -> MarketMonitorTraceDetail:
    try:
        return market_monitor_service.get_trace_detail(trace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Market monitor trace not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/api/market-monitor/traces/{trace_id}/logs",
    response_model=list[MarketMonitorTraceLogEntry],
)
def get_market_monitor_trace_logs(trace_id: str) -> list[MarketMonitorTraceLogEntry]:
    try:
        return market_monitor_service.list_trace_logs(trace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Market monitor trace not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def run_api() -> None:
    uvicorn.run("tradingagents.web.api.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_api()
