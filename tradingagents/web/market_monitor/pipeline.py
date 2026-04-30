from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

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
from tradingagents.web.market_monitor.trading_calendar import resolve_market_monitor_as_of_date


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
        log: Callable[[str], None] | None = None,
    ) -> MarketMonitorExecutionResult:
        if request.trigger_endpoint == "snapshot":
            as_of_date = resolve_market_monitor_as_of_date(request.as_of_date, request.data_mode)
            _log(log, f"开始生成单日快照：美东交易日={as_of_date.isoformat()}")
            snapshot = service.get_snapshot(
                MarketMonitorSnapshotRequest(
                    as_of_date=as_of_date,
                    force_refresh=request.force_refresh,
                    data_mode=request.data_mode,
                ),
                previous_snapshots=previous_snapshots,
                log=log,
            ).model_copy(update={"run_id": run_id})
            _log(log, f"单日快照生成完成：美东交易日={snapshot.as_of_date.isoformat()}")
            return MarketMonitorExecutionResult(
                snapshot=snapshot,
                fact_sheet=snapshot.fact_sheet,
                prompt_traces=list(snapshot.prompt_traces),
            )
        if request.trigger_endpoint == "history":
            as_of_date = resolve_market_monitor_as_of_date(request.as_of_date, request.data_mode)
            history_request = MarketMonitorHistoryRequest(
                as_of_date=as_of_date,
                days=request.days or 20,
                force_refresh=request.force_refresh,
                data_mode=request.data_mode,
            )
            trade_dates = service.resolve_history_trade_dates(history_request)
            if trade_dates:
                _log(
                    log,
                    (
                        f"历史回放日期已解析：请求 {history_request.days} 天，实际交易日 {len(trade_dates)} 个，"
                        f"范围 {trade_dates[0].isoformat()} 至 {trade_dates[-1].isoformat()}"
                    ),
                )
            else:
                _log(log, f"历史回放日期已解析：请求 {history_request.days} 天，实际交易日 0 个")
            history_snapshots = [
                snapshot.model_copy(update={"run_id": run_id})
                for snapshot in service.get_history_snapshots(history_request, trade_dates, previous_snapshots=previous_snapshots, log=log)
            ]
            history = service.build_history_response(
                history_request.as_of_date,
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
        as_of_date = resolve_market_monitor_as_of_date(request.as_of_date, request.data_mode)
        _log(log, f"开始生成数据状态：美东交易日={as_of_date.isoformat()}")
        data_status = service.get_data_status(
            MarketMonitorSnapshotRequest(
                as_of_date=as_of_date,
                force_refresh=request.force_refresh,
                data_mode=request.data_mode,
            ),
            log=log,
        ).model_copy(update={"run_id": run_id})
        _log(log, f"数据状态生成完成：美东交易日={data_status.as_of_date.isoformat()}")
        return MarketMonitorExecutionResult(
            data_status=data_status,
            fact_sheet=data_status.fact_sheet,
        )


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is not None:
        log(message)
