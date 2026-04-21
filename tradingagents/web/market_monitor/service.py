from __future__ import annotations

from tradingagents.web.market_monitor.pipeline import MarketMonitorExecutionResult, MarketMonitorPipeline
from tradingagents.web.market_monitor.schemas import MarketMonitorRunRequest
from tradingagents.web.market_monitor.snapshot_service import MarketMonitorSnapshotService


class MarketMonitorRunService:
    def __init__(self, snapshot_service: MarketMonitorSnapshotService, pipeline: MarketMonitorPipeline) -> None:
        self.snapshot_service = snapshot_service
        self.pipeline = pipeline

    def execute(self, request: MarketMonitorRunRequest, run_id: str) -> MarketMonitorExecutionResult:
        return self.pipeline.execute(request=request, run_id=run_id, service=self.snapshot_service)
