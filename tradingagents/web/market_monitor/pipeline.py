from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from tradingagents.web.market_monitor.schemas import (
    MarketMonitorDataStatusResponse,
    MarketMonitorFactSheet,
    MarketMonitorHistoryRequest,
    MarketMonitorHistoryResponse,
    MarketMonitorPromptTrace,
    MarketMonitorRunRequest,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
)
from tradingagents.web.market_monitor.snapshot_service import MarketMonitorSnapshotService


@dataclass
class MarketMonitorExecutionResult:
    snapshot: MarketMonitorSnapshotResponse | None = None
    history: MarketMonitorHistoryResponse | None = None
    data_status: MarketMonitorDataStatusResponse | None = None
    fact_sheet: MarketMonitorFactSheet | None = None
    prompt_traces: list[MarketMonitorPromptTrace] = field(default_factory=list)
    history_snapshots: list[MarketMonitorSnapshotResponse] = field(default_factory=list)


class MarketMonitorPipeline:
    def execute(
        self,
        *,
        request: MarketMonitorRunRequest,
        run_id: str,
        service: MarketMonitorSnapshotService,
        previous_snapshots: list[MarketMonitorSnapshotResponse] | None = None,
    ) -> MarketMonitorExecutionResult:
        if request.trigger_endpoint == "snapshot":
            snapshot = service.get_snapshot(
                MarketMonitorSnapshotRequest(
                    as_of_date=request.as_of_date,
                    force_refresh=request.force_refresh,
                    data_mode=request.data_mode,
                ),
                previous_snapshots=previous_snapshots,
            ).model_copy(update={"run_id": run_id})
            return MarketMonitorExecutionResult(
                snapshot=snapshot,
                fact_sheet=snapshot.fact_sheet,
                prompt_traces=list(snapshot.prompt_traces),
            )
        if request.trigger_endpoint == "history":
            history_request = MarketMonitorHistoryRequest(
                as_of_date=request.as_of_date,
                days=request.days or 20,
                force_refresh=request.force_refresh,
                data_mode=request.data_mode,
            )
            trade_dates = service.resolve_history_trade_dates(history_request)
            history_snapshots = [
                snapshot.model_copy(update={"run_id": run_id})
                for snapshot in service.get_history_snapshots(history_request, trade_dates, previous_snapshots=previous_snapshots)
            ]
            history = service.build_history_response(
                history_request.as_of_date or date.today(),
                history_snapshots,
            ).model_copy(update={"run_id": run_id})
            latest_fact_sheet = None
            prompt_traces: list[MarketMonitorPromptTrace] = []
            for snapshot in history_snapshots:
                prompt_traces.extend(snapshot.prompt_traces)
                if snapshot.fact_sheet is not None:
                    latest_fact_sheet = snapshot.fact_sheet
            return MarketMonitorExecutionResult(
                history=history,
                fact_sheet=latest_fact_sheet,
                prompt_traces=prompt_traces,
                history_snapshots=history_snapshots,
            )
        data_status = service.get_data_status(
            MarketMonitorSnapshotRequest(
                as_of_date=request.as_of_date,
                force_refresh=request.force_refresh,
                data_mode=request.data_mode,
            )
        ).model_copy(update={"run_id": run_id})
        return MarketMonitorExecutionResult(
            data_status=data_status,
            fact_sheet=data_status.fact_sheet,
        )
