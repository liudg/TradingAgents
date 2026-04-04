import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from cli.models import AnalystType
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS
from tradingagents.web.job_manager import AnalysisJobManager
from tradingagents.web.schemas import (
    AnalysisJobCreateResponse,
    AnalysisJobLogEntry,
    AnalysisJobRequest,
    AnalysisJobResponse,
    HistoricalReportDetail,
    HistoricalReportSummary,
    MetadataOptionsResponse,
)


load_dotenv()

app = FastAPI(
    title="TradingAgents Web API",
    description="Async HTTP API wrapper for TradingAgents analysis jobs.",
    version="0.2.3",
)
job_manager = AnalysisJobManager()


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


def run_api() -> None:
    uvicorn.run("tradingagents.web.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_api()
