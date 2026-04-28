from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from .data import _expected_market_close_date, build_market_dataset
from .fact_sheet import build_market_fact_sheet
from .factors import (
    build_event_fact_sheet,
    build_execution_card,
    build_input_bundle,
    build_long_term_card,
    build_panic_card,
    build_short_term_card,
    build_style_effectiveness,
    build_system_risk_card,
)
from .inference.cards import MarketMonitorCardInferenceService
from .inference.execution import MarketMonitorExecutionInferenceService
from .metrics import build_market_snapshot
from .schemas import (
    MarketMonitorDataStatusResponse,
    MarketMonitorFactSheet,
    MarketMonitorHistoryPoint,
    MarketMonitorHistoryRequest,
    MarketMonitorMissingDataItem,
    MarketMonitorHistoryResponse,
    MarketMonitorRunLlmConfig,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
)
from .universe import get_market_monitor_universe


class MarketMonitorSnapshotService:
    def __init__(self, llm_config: MarketMonitorRunLlmConfig | None = None) -> None:
        self._universe = get_market_monitor_universe()
        self._inference = MarketMonitorCardInferenceService(llm_config)
        self._execution_inference = MarketMonitorExecutionInferenceService(llm_config)

    def get_snapshot(
        self,
        request: MarketMonitorSnapshotRequest,
        previous_snapshots: list[MarketMonitorSnapshotResponse] | None = None,
    ) -> MarketMonitorSnapshotResponse:
        as_of_date = request.as_of_date or date.today()
        dataset = build_market_dataset(self._universe, as_of_date, force_refresh=request.force_refresh)
        return self._build_snapshot(as_of_date, dataset, previous_snapshots=previous_snapshots)

    def get_history(self, request: MarketMonitorHistoryRequest) -> MarketMonitorHistoryResponse:
        as_of_date = request.as_of_date or date.today()
        snapshots = self.get_history_snapshots(request)
        return self.build_history_response(as_of_date, snapshots)

    def resolve_history_trade_dates(self, request: MarketMonitorHistoryRequest) -> list[date]:
        as_of_date = request.as_of_date or date.today()
        trade_dates: list[date] = []
        cursor = as_of_date
        attempts = 0
        while len(trade_dates) < request.days and attempts < request.days * 3:
            attempts += 1
            if _expected_market_close_date(cursor).date() != cursor:
                cursor -= timedelta(days=1)
                continue
            trade_dates.append(cursor)
            cursor -= timedelta(days=1)
        trade_dates.sort()
        return trade_dates

    def get_history_snapshots(
        self,
        request: MarketMonitorHistoryRequest,
        trade_dates: list[date] | None = None,
        previous_snapshots: list[MarketMonitorSnapshotResponse] | None = None,
    ) -> list[MarketMonitorSnapshotResponse]:
        dates_to_build = trade_dates or self.resolve_history_trade_dates(request)
        snapshots: list[MarketMonitorSnapshotResponse] = []
        context = list(previous_snapshots or [])
        for trade_date in dates_to_build:
            dataset = build_market_dataset(self._universe, trade_date, force_refresh=request.force_refresh, include_event_news=False)
            snapshot = self._build_snapshot(trade_date, dataset, previous_snapshots=context)
            snapshots.append(snapshot)
            context.append(snapshot)
        snapshots.sort(key=lambda item: item.as_of_date)
        return snapshots

    def build_history_response(
        self,
        as_of_date: date,
        snapshots: list[MarketMonitorSnapshotResponse],
    ) -> MarketMonitorHistoryResponse:
        return MarketMonitorHistoryResponse(
            as_of_date=as_of_date,
            points=[
                MarketMonitorHistoryPoint(
                    trade_date=snapshot.as_of_date,
                    scorecard_version=snapshot.scorecard_version,
                    long_term_score=snapshot.long_term_score.score,
                    short_term_score=snapshot.short_term_score.score,
                    system_risk_score=snapshot.system_risk_score.score,
                    panic_reversal_score=snapshot.panic_reversal_score.score,
                    panic_state=snapshot.panic_reversal_score.state,
                    regime_label=snapshot.execution_card.regime_label,
                )
                for snapshot in snapshots
            ],
        )

    def get_data_status(self, request: MarketMonitorSnapshotRequest) -> MarketMonitorDataStatusResponse:
        as_of_date = request.as_of_date or date.today()
        dataset = build_market_dataset(self._universe, as_of_date, force_refresh=request.force_refresh)
        snapshot = self._build_snapshot(as_of_date, dataset)
        return MarketMonitorDataStatusResponse(
            timestamp=snapshot.timestamp,
            as_of_date=snapshot.as_of_date,
            data_mode=snapshot.data_mode,
            data_freshness=snapshot.data_freshness,
            input_data_status=snapshot.input_data_status,
            missing_data=snapshot.missing_data,
            open_gaps=snapshot.fact_sheet.open_gaps if snapshot.fact_sheet else [],
            risks=snapshot.risks,
            event_fact_sheet=snapshot.event_fact_sheet,
            fact_sheet=snapshot.fact_sheet,
        )

    def _build_snapshot(
        self,
        as_of_date: date,
        dataset: dict[str, Any],
        fact_sheet_override: MarketMonitorFactSheet | None = None,
        previous_snapshots: list[MarketMonitorSnapshotResponse] | None = None,
    ) -> MarketMonitorSnapshotResponse:
        bundle = build_input_bundle(
            as_of_date=as_of_date,
            dataset=dataset,
            universe=self._universe,
        )
        core_data = dataset["core"]
        local_market_data, derived_metrics = build_market_snapshot(core_data, self._universe["breadth_proxy_symbols"])
        event_fact_sheet = fact_sheet_override.event_fact_sheet if fact_sheet_override else build_event_fact_sheet(bundle)
        if not event_fact_sheet and not any(item.field in {"event_fact_sheet", "search.event_fact_candidates"} for item in bundle.missing_data):
            bundle.missing_data.append(
                MarketMonitorMissingDataItem(
                    field="event_fact_sheet",
                    reason="当前刷新周期未注入联网搜索事件事实",
                    impact="宏观日历、财报日历和突发事件只能按空事实表处理，不得编造事件",
                    severity="medium",
                )
            )
        open_gaps = self._build_open_gaps(bundle, event_fact_sheet)
        notes = [item.reason for item in bundle.missing_data]
        fact_sheet = fact_sheet_override or build_market_fact_sheet(
            as_of_date=as_of_date,
            generated_at=bundle.timestamp,
            core_data=core_data,
            local_market_data=local_market_data,
            derived_metrics=derived_metrics,
            open_gaps=open_gaps,
            notes=notes,
            event_fact_sheet=event_fact_sheet,
        )

        long_term_deterministic = build_long_term_card(bundle)
        short_term_deterministic = build_short_term_card(bundle)
        system_risk_deterministic = build_system_risk_card(bundle, event_fact_sheet)
        style_deterministic = build_style_effectiveness(bundle)

        long_term_result = self._inference.infer_long_term(
            fact_sheet,
            long_term_deterministic,
            lambda: long_term_deterministic,
        )
        short_term_result = self._inference.infer_short_term(
            fact_sheet,
            short_term_deterministic,
            lambda: short_term_deterministic,
        )
        system_risk_result = self._inference.infer_system_risk(
            fact_sheet,
            system_risk_deterministic,
            lambda: system_risk_deterministic,
        )
        style_result = self._inference.infer_style(
            fact_sheet,
            style_deterministic,
            lambda: style_deterministic,
        )

        long_term = long_term_result.payload
        short_term = short_term_result.payload
        system_risk = system_risk_result.payload
        style = style_result.payload
        panic_deterministic = build_panic_card(bundle, system_risk.score, previous_snapshots=previous_snapshots)
        panic_result = self._inference.infer_panic(
            fact_sheet,
            panic_deterministic,
            lambda: panic_deterministic,
        )
        panic = panic_result.payload
        execution_fallback = lambda: build_execution_card(
            long_term,
            short_term,
            system_risk,
            style,
            event_fact_sheet,
            panic,
            previous_snapshots=previous_snapshots,
        )
        execution_result = self._execution_inference.infer_execution(
            fact_sheet=fact_sheet,
            long_term=long_term,
            short_term=short_term,
            system_risk=system_risk,
            style=style,
            panic=panic,
            event_fact_sheet=event_fact_sheet,
            fallback=execution_fallback,
        )
        prompt_traces = [
            long_term_result.trace,
            short_term_result.trace,
            system_risk_result.trace,
            style_result.trace,
            panic_result.trace,
            execution_result.trace,
        ]
        return MarketMonitorSnapshotResponse(
            model_name=self._inference.runner.llm_config.model,
            timestamp=bundle.timestamp,
            as_of_date=as_of_date,
            data_mode=bundle.data_mode,
            data_freshness=bundle.data_freshness,
            input_data_status=bundle.input_data_status,
            missing_data=bundle.missing_data,
            risks=bundle.risks,
            event_fact_sheet=event_fact_sheet,
            long_term_score=long_term,
            short_term_score=short_term,
            system_risk_score=system_risk,
            style_effectiveness=style,
            execution_card=execution_result.payload,
            panic_reversal_score=panic,
            fact_sheet=fact_sheet,
            prompt_traces=prompt_traces,
        )

    def _build_open_gaps(self, bundle: Any, event_fact_sheet: list[Any]) -> list[str]:
        gaps = [f"缺少 {symbol} 日线" for symbol in bundle.input_data_status.core_symbols_missing]
        if not event_fact_sheet:
            gaps.append("未注入宏观日历、财报日历、政策/地缘与突发新闻搜索事实")
        return gaps
