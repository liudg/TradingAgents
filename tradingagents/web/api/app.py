from datetime import date

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
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
from tradingagents.web.market_monitor.manager import MarketMonitorRunManager
from tradingagents.web.market_monitor.schemas import (
    HistoricalMarketMonitorRunDetail,
    HistoricalMarketMonitorRunSummary,
    MarketMonitorDataStatusResponse,
    MarketMonitorHistoryRequest,
    MarketMonitorHistoryResponse,
    MarketMonitorPromptTrace,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
)


load_dotenv()

app = FastAPI(
    title="TradingAgents Web API",
    description="Async HTTP API wrapper for TradingAgents analysis jobs.",
    version="0.2.3",
)
job_manager = AnalysisJobManager()
backtest_manager = BacktestJobManager()
market_monitor_manager = MarketMonitorRunManager()
market_monitor_service = market_monitor_manager.service


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
def get_market_monitor_snapshot(
    as_of_date: date | None = None,
    force_refresh: bool = False,
) -> MarketMonitorSnapshotResponse:
    request = MarketMonitorSnapshotRequest(
        as_of_date=as_of_date,
        force_refresh=force_refresh,
    )
    return market_monitor_manager.run_snapshot(request)


@app.get("/api/market-monitor/history", response_model=MarketMonitorHistoryResponse)
def get_market_monitor_history(
    as_of_date: date | None = None,
    days: int = 20,
    force_refresh: bool = False,
) -> MarketMonitorHistoryResponse:
    request = MarketMonitorHistoryRequest(
        as_of_date=as_of_date,
        days=days,
        force_refresh=force_refresh,
    )
    return market_monitor_manager.run_history(request)


@app.get("/api/market-monitor/data-status", response_model=MarketMonitorDataStatusResponse)
def get_market_monitor_data_status(
    as_of_date: date | None = None,
    force_refresh: bool = False,
) -> MarketMonitorDataStatusResponse:
    request = MarketMonitorSnapshotRequest(
        as_of_date=as_of_date,
        force_refresh=force_refresh,
    )
    return market_monitor_manager.run_data_status(request)


@app.get("/api/market-monitor/runs", response_model=list[HistoricalMarketMonitorRunSummary])
def list_market_monitor_runs() -> list[HistoricalMarketMonitorRunSummary]:
    return market_monitor_manager.list_historical_runs()


@app.get(
    "/api/market-monitor/runs/{run_id}",
    response_model=HistoricalMarketMonitorRunDetail,
)
def get_market_monitor_run(run_id: str) -> HistoricalMarketMonitorRunDetail:
    try:
        return market_monitor_manager.get_historical_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Market monitor run not found") from exc


@app.get(
    "/api/market-monitor/runs/{run_id}/logs",
    response_model=list[AnalysisJobLogEntry],
)
def get_market_monitor_run_logs(run_id: str) -> list[AnalysisJobLogEntry]:
    try:
        return market_monitor_manager.list_run_logs(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Market monitor run not found") from exc


@app.get(
    "/api/market-monitor/runs/{run_id}/prompt-traces",
    response_model=list[MarketMonitorPromptTrace],
)
def get_market_monitor_prompt_traces(run_id: str) -> list[MarketMonitorPromptTrace]:
    try:
        return market_monitor_manager.list_prompt_traces(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Market monitor run not found") from exc


@app.get("/api/market-monitor/runs/{run_id}/artifacts/{artifact_name}")
def get_market_monitor_artifact(run_id: str, artifact_name: str) -> dict:
    try:
        return market_monitor_manager.read_artifact_payload(run_id, artifact_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Market monitor run not found") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Market monitor artifact not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/api/market-monitor/runs/{run_id}/recover",
    response_model=HistoricalMarketMonitorRunDetail,
)
def recover_market_monitor_run(run_id: str) -> HistoricalMarketMonitorRunDetail:
    try:
        return market_monitor_manager.recover_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Market monitor run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def run_api() -> None:
    uvicorn.run("tradingagents.web.api.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_api()
