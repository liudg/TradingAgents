from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Callable

from .data import build_market_dataset
from .trading_calendar import is_us_market_trading_day, resolve_market_monitor_as_of_date
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
    MarketMonitorHistoryResponse,
    MarketMonitorMissingDataItem,
    MarketMonitorRunLlmConfig,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
)
from .universe import get_market_monitor_universe


class MarketMonitorSnapshotService:
    def __init__(self, llm_config: MarketMonitorRunLlmConfig | None = None) -> None:
        self._universe = get_market_monitor_universe()
        self._llm_config = llm_config
        self._inference = MarketMonitorCardInferenceService(llm_config)
        self._execution_inference = MarketMonitorExecutionInferenceService(llm_config)

    def get_snapshot(
        self,
        request: MarketMonitorSnapshotRequest,
        previous_snapshots: list[MarketMonitorSnapshotResponse] | None = None,
        log: Callable[[str], None] | None = None,
    ) -> MarketMonitorSnapshotResponse:
        as_of_date = resolve_market_monitor_as_of_date(request.as_of_date, request.data_mode)
        _log(log, f"开始读取市场数据：美东交易日={as_of_date.isoformat()}，模式={request.data_mode}，force_refresh={str(request.force_refresh).lower()}")
        dataset = build_market_dataset(self._universe, as_of_date, force_refresh=request.force_refresh, data_mode=request.data_mode)
        return self._build_snapshot(as_of_date, dataset, previous_snapshots=previous_snapshots, log=log)

    def get_history(self, request: MarketMonitorHistoryRequest) -> MarketMonitorHistoryResponse:
        as_of_date = resolve_market_monitor_as_of_date(request.as_of_date, request.data_mode)
        snapshots = self.get_history_snapshots(request.model_copy(update={"as_of_date": as_of_date}))
        return self.build_history_response(as_of_date, snapshots)

    def resolve_history_trade_dates(self, request: MarketMonitorHistoryRequest) -> list[date]:
        as_of_date = resolve_market_monitor_as_of_date(request.as_of_date, request.data_mode)
        trade_dates: list[date] = []
        cursor = as_of_date
        attempts = 0
        while len(trade_dates) < request.days and attempts < request.days * 3:
            attempts += 1
            if not is_us_market_trading_day(cursor):
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
        log: Callable[[str], None] | None = None,
    ) -> list[MarketMonitorSnapshotResponse]:
        dates_to_build = trade_dates or self.resolve_history_trade_dates(request)
        snapshots: list[MarketMonitorSnapshotResponse] = []
        context = list(previous_snapshots or [])
        total = len(dates_to_build)
        for index, trade_date in enumerate(dates_to_build, start=1):
            _log(log, f"开始生成历史快照：{index}/{total}，美东交易日={trade_date.isoformat()}")
            _log(log, f"开始读取市场数据：美东交易日={trade_date.isoformat()}，模式={request.data_mode}，force_refresh={str(request.force_refresh).lower()}")
            dataset = build_market_dataset(
                self._universe,
                trade_date,
                force_refresh=request.force_refresh,
                include_event_news=False,
                data_mode=request.data_mode,
            )
            snapshot = self._build_snapshot(trade_date, dataset, previous_snapshots=context, log=log)
            snapshots.append(snapshot)
            context.append(snapshot)
            _log(log, f"历史快照生成完成：{index}/{total}，美东交易日={snapshot.as_of_date.isoformat()}")
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

    def get_data_status(
        self,
        request: MarketMonitorSnapshotRequest,
        log: Callable[[str], None] | None = None,
    ) -> MarketMonitorDataStatusResponse:
        as_of_date = resolve_market_monitor_as_of_date(request.as_of_date, request.data_mode)
        _log(log, f"开始读取市场数据：美东交易日={as_of_date.isoformat()}，模式={request.data_mode}，force_refresh={str(request.force_refresh).lower()}")
        dataset = build_market_dataset(self._universe, as_of_date, force_refresh=request.force_refresh, data_mode=request.data_mode)
        snapshot = self._build_snapshot(as_of_date, dataset, log=log)
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
        log: Callable[[str], None] | None = None,
    ) -> MarketMonitorSnapshotResponse:
        _log(log, "开始构建输入特征与事实表")
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
        _log_data_quality(log, bundle.input_data_status)
        _log(
            log,
            f"事实表构建完成：事件事实 {len(event_fact_sheet)} 条，开放缺口 {len(open_gaps)} 项，缺失数据 {len(bundle.missing_data)} 项",
        )

        long_term_deterministic = build_long_term_card(bundle)
        short_term_deterministic = build_short_term_card(bundle)
        system_risk_deterministic = build_system_risk_card(bundle, event_fact_sheet)
        style_deterministic = build_style_effectiveness(bundle)
        _log(
            log,
            (
                "确定性评分完成："
                f"长线={long_term_deterministic.score:.1f}，"
                f"短线={short_term_deterministic.score:.1f}，"
                f"系统风险={system_risk_deterministic.score:.1f}，风格层已生成"
            ),
        )

        def card_inference() -> MarketMonitorCardInferenceService:
            return MarketMonitorCardInferenceService(self._llm_config)

        _log(log, "开始 LLM 推理：长线/短线/系统风险/风格卡并发执行")
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="market-monitor-card") as executor:
            long_term_future = executor.submit(
                lambda: card_inference().infer_long_term(
                    fact_sheet,
                    long_term_deterministic,
                    lambda: long_term_deterministic,
                )
            )
            short_term_future = executor.submit(
                lambda: card_inference().infer_short_term(
                    fact_sheet,
                    short_term_deterministic,
                    lambda: short_term_deterministic,
                )
            )
            system_risk_future = executor.submit(
                lambda: card_inference().infer_system_risk(
                    fact_sheet,
                    system_risk_deterministic,
                    lambda: system_risk_deterministic,
                )
            )
            style_future = executor.submit(
                lambda: card_inference().infer_style(
                    fact_sheet,
                    style_deterministic,
                    lambda: style_deterministic,
                )
            )

            system_risk_result = system_risk_future.result()
            _log_inference_result(log, "系统风险卡", system_risk_result)
            system_risk = system_risk_result.payload
            panic_deterministic = build_panic_card(bundle, system_risk.score, previous_snapshots=previous_snapshots)
            _log(log, "开始 LLM 推理：恐慌反转卡")
            panic_result = card_inference().infer_panic(
                fact_sheet,
                panic_deterministic,
                lambda: panic_deterministic,
            )
            _log_inference_result(log, "恐慌反转卡", panic_result)
            long_term_result = long_term_future.result()
            _log_inference_result(log, "长线环境卡", long_term_result)
            short_term_result = short_term_future.result()
            _log_inference_result(log, "短线环境卡", short_term_result)
            style_result = style_future.result()
            _log_inference_result(log, "风格有效性卡", style_result)

        long_term = long_term_result.payload
        short_term = short_term_result.payload
        style = style_result.payload
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
        _log(log, "开始 LLM 推理：执行建议卡")
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
        _log_inference_result(log, "执行建议卡", execution_result)
        prompt_traces = [
            long_term_result.trace,
            short_term_result.trace,
            system_risk_result.trace,
            style_result.trace,
            panic_result.trace,
            execution_result.trace,
        ]
        _log(log, f"快照组装完成：regime={execution_result.payload.regime_label}，Prompt trace {len(prompt_traces)} 条")
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
        interval = bundle.input_data_status.interval
        gaps = [f"缺少 {symbol} {interval} 行情" for symbol in bundle.input_data_status.core_symbols_missing]
        if not event_fact_sheet:
            gaps.append("未注入宏观日历、财报日历、政策/地缘与突发新闻搜索事实")
        return gaps


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is not None:
        log(message)


def _log_data_quality(log: Callable[[str], None] | None, input_status: Any) -> None:
    _log(
        log,
        (
            "市场数据读取完成："
            f"可用核心标的 {len(input_status.core_symbols_available)} 个，"
            f"缺失 {len(input_status.core_symbols_missing)} 个，"
            f"陈旧 {len(input_status.stale_symbols)} 个，"
            f"部分可用 {len(input_status.partial_symbols)} 个"
        ),
    )
    if input_status.core_symbols_missing:
        _log(log, f"数据质量提示：缺失核心标的 {len(input_status.core_symbols_missing)} 个：{_summarize_symbols(input_status.core_symbols_missing)}")
    if input_status.stale_symbols:
        _log(log, f"数据质量提示：陈旧标的 {len(input_status.stale_symbols)} 个：{_summarize_symbols(input_status.stale_symbols)}")
    if input_status.partial_symbols:
        _log(log, f"数据质量提示：部分可用标的 {len(input_status.partial_symbols)} 个：{_summarize_symbols(input_status.partial_symbols)}")


def _log_inference_result(log: Callable[[str], None] | None, title: str, result: Any) -> None:
    trace = result.trace
    parsed = "成功" if trace.parsed_ok else "失败"
    fallback = "是" if result.used_fallback else "否"
    latency = f"，耗时={trace.latency_ms}ms" if trace.latency_ms is not None else ""
    error = f"，错误={_short_error(trace.error)}" if trace.error else ""
    _log(log, f"LLM 推理完成：{title}，解析={parsed}，fallback={fallback}{latency}{error}")


def _summarize_symbols(symbols: list[str], limit: int = 5) -> str:
    shown = symbols[:limit]
    suffix = f" 等 {len(symbols)} 个" if len(symbols) > limit else ""
    return ", ".join(shown) + suffix


def _short_error(error: str, limit: int = 200) -> str:
    compact = " ".join(error.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."
