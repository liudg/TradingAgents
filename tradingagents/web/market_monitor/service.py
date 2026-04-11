from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .cache import (
    latest_symbol_cache_mtime,
    load_snapshot_cache,
    save_snapshot_cache,
)
from .data import _expected_market_close_date, build_market_dataset
from .llm import MarketMonitorLLMService
from .schemas import (
    MarketEventRiskFlag,
    MarketExecutionCard,
    MarketExecutionSignalConfirmation,
    MarketHistoryPoint,
    MarketIndexEventRisk,
    MarketMonitorDataStatusResponse,
    MarketMonitorHistoryResponse,
    MarketMonitorModelOverlay,
    MarketMonitorRuleSnapshot,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
    MarketMonitorTraceDetail,
    MarketMonitorTraceLogEntry,
    MarketMonitorTraceSummary,
    MarketPanicReversalCard,
    MarketScoreCard,
    MarketSourceCoverage,
    MarketStockEventRisk,
    MarketStyleAssetLayer,
    MarketStyleEffectiveness,
    MarketStyleSignal,
    MarketStyleTacticLayer,
)
from .scoring import (
    LONG_TERM_ZONES,
    SHORT_TERM_ZONES,
    SYSTEM_RISK_ZONES,
    build_breadth_ratio,
    build_long_term_series,
    build_short_term_series,
    build_system_risk_series,
    score_asset_layer,
    score_tactic_layer,
    summarize_score,
)
from .trace import MarketMonitorTraceLogger, MarketMonitorTraceStore
from .universe import get_market_monitor_universe


class MarketMonitorService:
    """Market monitor service using live yfinance data and optional model overlay."""

    _LIVE_CACHE_TTL_SECONDS = 300

    def __init__(self, trace_root: Path | None = None) -> None:
        self._overlay_service = MarketMonitorLLMService()
        self._dataset_cache: dict[date, dict[str, Any]] = {}
        self._trace_store = MarketMonitorTraceStore(trace_root)

    def get_snapshot(self, request: MarketMonitorSnapshotRequest) -> MarketMonitorSnapshotResponse:
        as_of_date = request.as_of_date or date.today()
        universe = get_market_monitor_universe()
        trace = self._trace_store.create_logger(as_of_date, request.force_refresh)
        trace.log_event(
            "Request",
            f"市场监控快照请求开始：{as_of_date.isoformat()}（force_refresh={request.force_refresh}）",
        )
        trace.set_stage(
            "request",
            {
                "as_of_date": as_of_date.isoformat(),
                "force_refresh": request.force_refresh,
                "universe_sizes": {
                    "all_symbols": len(universe["all_symbols"]),
                    "market_proxies": len(universe["market_proxies"]),
                    "sector_etfs": len(universe["sector_etfs"]),
                },
            },
        )

        try:
            if request.force_refresh:
                trace.log_event("Cache", "force_refresh=True，跳过快照缓存")
                trace.set_stage(
                    "cache_decision",
                    {
                        "snapshot_cache_checked": False,
                        "snapshot_cache_hit": False,
                        "dataset_cache_hit": False,
                        "reason": "force_refresh",
                    },
                )
            else:
                cached_snapshot = load_snapshot_cache(as_of_date)
                snapshot_cache_hit = False
                cache_reason = "snapshot_cache_miss"
                if cached_snapshot is not None:
                    snapshot_cache_hit = self._is_snapshot_cache_usable(cached_snapshot, as_of_date, universe)
                    cache_reason = "snapshot_cache_hit" if snapshot_cache_hit else "snapshot_cache_unusable"
                trace.log_event("Cache", f"快照缓存决策：{cache_reason}")
                if snapshot_cache_hit:
                    snapshot = MarketMonitorSnapshotResponse.model_validate(cached_snapshot)
                    snapshot.trace_id = trace.trace_id
                    trace.set_stage(
                        "dataset_summary",
                        {
                            "source": "snapshot_cache",
                            "available_symbol_count": None,
                            "market_proxy_count": len(universe["market_proxies"]),
                            "missing_required_symbols": list(snapshot.rule_snapshot.missing_inputs),
                            "available_symbols_sample": [],
                            "symbol_rows": {},
                        },
                    )
                    trace.set_stage(
                        "rule_snapshot_summary",
                        self._summarize_rule_snapshot(snapshot.rule_snapshot),
                    )
                    trace.set_stage(
                        "overlay_summary",
                        self._summarize_overlay(snapshot.model_overlay, []),
                    )
                    trace.set_stage(
                        "final_execution_summary",
                        self._summarize_final_execution(
                            snapshot.rule_snapshot,
                            snapshot.model_overlay,
                            snapshot.final_execution_card,
                        ),
                    )
                    trace.set_summary_fields(
                        rule_ready=snapshot.rule_snapshot.ready,
                        base_regime_label=snapshot.rule_snapshot.base_regime_label,
                        final_regime_label=(
                            snapshot.final_execution_card.regime_label if snapshot.final_execution_card else None
                        ),
                        overlay_status=snapshot.model_overlay.status,
                    )
                    trace.set_stage(
                        "cache_decision",
                        {
                            "snapshot_cache_checked": True,
                            "snapshot_cache_hit": True,
                            "dataset_cache_hit": False,
                            "reason": cache_reason,
                        },
                    )
                    trace.log_event("Response", "返回缓存快照")
                    trace.complete(
                        {
                            "served_from_snapshot_cache": True,
                            "snapshot_cache_written": False,
                            "trace_id": trace.trace_id,
                        }
                    )
                    return snapshot
                trace.set_stage(
                    "cache_decision",
                    {
                        "snapshot_cache_checked": True,
                        "snapshot_cache_hit": False,
                        "dataset_cache_hit": False,
                        "reason": cache_reason,
                    },
                )

            dataset, dataset_meta = self._get_dataset(
                universe,
                as_of_date,
                force_refresh=request.force_refresh,
                trace=trace,
            )
            trace.set_stage("dataset_summary", dataset_meta)
            rule_snapshot = self._build_rule_snapshot(dataset, universe)
            rule_summary = self._summarize_rule_snapshot(rule_snapshot)
            trace.set_stage("rule_snapshot_summary", rule_summary)
            trace.set_summary_fields(
                rule_ready=rule_snapshot.ready,
                base_regime_label=rule_snapshot.base_regime_label,
            )
            trace.log_event(
                "Rule",
                f"规则快照 ready={rule_snapshot.ready}，基础状态={rule_snapshot.base_regime_label}",
            )
            context_queries = self._build_context_queries(rule_snapshot)
            trace.log_event("Overlay", f"已生成 {len(context_queries)} 条上下文查询")
            model_overlay = self._overlay_service.create_overlay(
                rule_snapshot,
                as_of_date.isoformat(),
                context_queries,
            )
            overlay_summary = self._summarize_overlay(model_overlay, context_queries)
            trace.set_stage("overlay_summary", overlay_summary)
            trace.set_summary_fields(overlay_status=model_overlay.status)
            trace.log_event("Overlay", f"模型叠加状态={model_overlay.status}")
            final_execution_card = self._merge_overlay(rule_snapshot, model_overlay)
            final_summary = self._summarize_final_execution(rule_snapshot, model_overlay, final_execution_card)
            trace.set_stage("final_execution_summary", final_summary)
            trace.set_summary_fields(final_regime_label=final_summary.get("final_regime_label"))
            trace.log_event(
                "Merge",
                f"最终执行状态={final_summary.get('final_regime_label')}，覆盖字段数={len(final_summary.get('overridden_fields', []))}",
            )

            response = MarketMonitorSnapshotResponse(
                timestamp=datetime.now(),
                as_of_date=as_of_date,
                trace_id=trace.trace_id,
                rule_snapshot=rule_snapshot,
                model_overlay=model_overlay,
                final_execution_card=final_execution_card,
            )
            snapshot_cache_written = False
            if self._is_snapshot_cacheable(response):
                save_snapshot_cache(as_of_date, response.model_dump(mode="json"))
                snapshot_cache_written = True
                trace.log_event("Cache", "已写入快照缓存")
            else:
                trace.log_event("Cache", "响应不可缓存，跳过快照缓存写入")
            trace.log_event("Response", "市场监控快照请求完成")
            trace.complete(
                {
                    "served_from_snapshot_cache": False,
                    "snapshot_cache_written": snapshot_cache_written,
                    "trace_id": trace.trace_id,
                }
            )
            return response
        except Exception as exc:
            trace.log_event("Error", f"{exc.__class__.__name__}: {exc}")
            trace.fail("snapshot", exc)
            raise

    def get_history(self, as_of_date: date, days: int = 10) -> MarketMonitorHistoryResponse:
        universe = get_market_monitor_universe()
        dataset, _ = self._get_dataset(universe, as_of_date)
        core_data = dataset["core"]
        missing_required = self._missing_required_symbols(core_data)
        if missing_required:
            return MarketMonitorHistoryResponse(as_of_date=as_of_date, points=[])

        breadth_ratio = build_breadth_ratio(core_data, universe["market_proxies"])
        sector_data = {symbol: core_data[symbol] for symbol in universe["sector_etfs"] if symbol in core_data}

        long_term_series = build_long_term_series(core_data, breadth_ratio).dropna().tail(days)
        short_term_series = (
            build_short_term_series(core_data, sector_data, breadth_ratio)
            .dropna()
            .reindex(long_term_series.index)
            .ffill()
        )
        system_risk_series = (
            build_system_risk_series(core_data, breadth_ratio)
            .dropna()
            .reindex(long_term_series.index)
            .ffill()
        )

        points: list[MarketHistoryPoint] = []
        for dt in long_term_series.index:
            long_score = float(long_term_series.loc[dt])
            short_score = float(short_term_series.loc[dt]) if dt in short_term_series.index else 50.0
            risk_score = float(system_risk_series.loc[dt]) if dt in system_risk_series.index else 50.0
            points.append(
                MarketHistoryPoint(
                    trade_date=dt.date(),
                    regime_label=self._regime_label(long_score, short_score, risk_score),
                    long_term_score=long_score,
                    short_term_score=short_score,
                    system_risk_score=risk_score,
                    panic_reversal_score=max(0.0, min(100.0, (100 - short_score) * 0.4 + risk_score * 0.6)),
                )
            )
        return MarketMonitorHistoryResponse(as_of_date=as_of_date, points=points)

    def get_data_status(self, as_of_date: date) -> MarketMonitorDataStatusResponse:
        cached_snapshot = load_snapshot_cache(as_of_date)
        universe = get_market_monitor_universe()
        if cached_snapshot is not None and self._is_snapshot_cache_usable(cached_snapshot, as_of_date, universe):
            snapshot = MarketMonitorSnapshotResponse.model_validate(cached_snapshot)
            return MarketMonitorDataStatusResponse(
                as_of_date=as_of_date,
                source_coverage=snapshot.rule_snapshot.source_coverage,
                available_sources=[
                    "live_yfinance_daily",
                    "etf_index_proxy_universe",
                    "fastapi_market_monitor",
                ],
                pending_sources=[
                    "intraday_panic_confirmation",
                    "put_call_ratio",
                    "vix_term_structure",
                    "calendar_events",
                    "web_search_overlay",
                ],
            )

        dataset, _ = self._get_dataset(universe, as_of_date)
        rule_snapshot = self._build_rule_snapshot(dataset, universe)
        return MarketMonitorDataStatusResponse(
            as_of_date=as_of_date,
            source_coverage=rule_snapshot.source_coverage,
            available_sources=[
                "live_yfinance_daily",
                "etf_index_proxy_universe",
                "fastapi_market_monitor",
            ],
            pending_sources=[
                "intraday_panic_confirmation",
                "put_call_ratio",
                "vix_term_structure",
                "calendar_events",
                "web_search_overlay",
            ],
        )

    def list_traces(
        self,
        as_of_date: date | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[MarketMonitorTraceSummary]:
        return self._trace_store.list_traces(as_of_date=as_of_date, status=status, limit=limit)

    def get_trace_detail(self, trace_id: str) -> MarketMonitorTraceDetail:
        return self._trace_store.get_trace_detail(trace_id)

    def list_trace_logs(self, trace_id: str) -> list[MarketMonitorTraceLogEntry]:
        return self._trace_store.list_trace_logs(trace_id)

    def _get_dataset(
        self,
        universe: dict[str, list[str]],
        as_of_date: date,
        force_refresh: bool = False,
        trace: MarketMonitorTraceLogger | None = None,
    ) -> tuple[dict[str, dict[str, pd.DataFrame]], dict[str, Any]]:
        if force_refresh:
            dataset = build_market_dataset(universe, as_of_date, force_refresh=True)
            self._save_dataset_cache(as_of_date, dataset, universe)
            meta = self._build_dataset_summary(dataset, universe, "live_refresh")
            if trace is not None:
                trace.log_event("Dataset", "force_refresh=True，已重建数据集")
                self._merge_trace_stage(trace, "cache_decision", {"dataset_cache_hit": False})
            return dataset, meta

        cached_entry = self._dataset_cache.get(as_of_date)
        if cached_entry is not None and self._is_dataset_cache_usable(cached_entry, as_of_date, universe):
            dataset = cached_entry["dataset"]
            meta = self._build_dataset_summary(dataset, universe, "memory_cache")
            if trace is not None:
                trace.log_event("Dataset", "复用内存中的数据集缓存")
                self._merge_trace_stage(trace, "cache_decision", {"dataset_cache_hit": True})
            return dataset, meta

        dataset = build_market_dataset(universe, as_of_date, force_refresh=False)
        self._save_dataset_cache(as_of_date, dataset, universe)
        meta = self._build_dataset_summary(dataset, universe, "live_request")
        if trace is not None:
            trace.log_event("Dataset", "已从市场数据源构建数据集")
            self._merge_trace_stage(trace, "cache_decision", {"dataset_cache_hit": False})
        return dataset, meta

    def _build_dataset_summary(
        self,
        dataset: dict[str, dict[str, pd.DataFrame]],
        universe: dict[str, list[str]],
        source: str,
    ) -> dict[str, Any]:
        core_data = dataset.get("core", {})
        available_symbols = sorted(
            symbol for symbol, frame in core_data.items() if frame is not None and not frame.empty
        )
        missing_required = self._missing_required_symbols(core_data)
        sample_symbols = ["SPY", "QQQ", "IWM", "^VIX"]
        symbol_rows = {
            symbol: self._summarize_frame(core_data.get(symbol))
            for symbol in sample_symbols
            if symbol in core_data
        }
        return {
            "source": source,
            "available_symbol_count": len(available_symbols),
            "market_proxy_count": len(universe["market_proxies"]),
            "missing_required_symbols": missing_required,
            "available_symbols_sample": available_symbols[:12],
            "symbol_rows": symbol_rows,
        }

    def _summarize_rule_snapshot(self, rule_snapshot: MarketMonitorRuleSnapshot) -> dict[str, Any]:
        return {
            "ready": rule_snapshot.ready,
            "base_regime_label": rule_snapshot.base_regime_label,
            "missing_inputs": list(rule_snapshot.missing_inputs),
            "degraded_factors": list(rule_snapshot.degraded_factors),
            "source_coverage": rule_snapshot.source_coverage.model_dump(mode="json"),
            "key_indicators": rule_snapshot.key_indicators,
            "long_term_score": (
                rule_snapshot.long_term_score.model_dump(mode="json")
                if rule_snapshot.long_term_score
                else None
            ),
            "short_term_score": (
                rule_snapshot.short_term_score.model_dump(mode="json")
                if rule_snapshot.short_term_score
                else None
            ),
            "system_risk_score": (
                rule_snapshot.system_risk_score.model_dump(mode="json")
                if rule_snapshot.system_risk_score
                else None
            ),
        }

    def _summarize_overlay(
        self,
        model_overlay: MarketMonitorModelOverlay,
        context_queries: list[str],
    ) -> dict[str, Any]:
        return {
            "status": model_overlay.status,
            "query_count": len(context_queries),
            "queries": context_queries,
            "regime_override": model_overlay.regime_override,
            "execution_adjustments": (
                model_overlay.execution_adjustments.model_dump(mode="json")
                if model_overlay.execution_adjustments
                else None
            ),
            "event_risk_override": (
                model_overlay.event_risk_override.model_dump(mode="json")
                if model_overlay.event_risk_override
                else None
            ),
            "evidence_sources": list(model_overlay.evidence_sources),
            "notes": list(model_overlay.notes),
            "model_confidence": model_overlay.model_confidence,
        }

    def _summarize_final_execution(
        self,
        rule_snapshot: MarketMonitorRuleSnapshot,
        model_overlay: MarketMonitorModelOverlay,
        final_execution_card: MarketExecutionCard | None,
    ) -> dict[str, Any]:
        overridden_fields = []
        if model_overlay.regime_override:
            overridden_fields.append("regime_override")
        if model_overlay.execution_adjustments:
            overridden_fields.extend(model_overlay.execution_adjustments.model_dump(exclude_none=True).keys())
        if model_overlay.event_risk_override:
            overridden_fields.append("event_risk_override")
        return {
            "base_regime_label": rule_snapshot.base_execution_card.regime_label
            if rule_snapshot.base_execution_card
            else None,
            "final_regime_label": final_execution_card.regime_label if final_execution_card else None,
            "base_execution_card": (
                rule_snapshot.base_execution_card.model_dump(mode="json")
                if rule_snapshot.base_execution_card
                else None
            ),
            "final_execution_card": (
                final_execution_card.model_dump(mode="json")
                if final_execution_card
                else None
            ),
            "overridden_fields": overridden_fields,
        }

    def _summarize_frame(self, frame: pd.DataFrame | None) -> dict[str, Any]:
        if frame is None or frame.empty:
            return {"rows": 0, "last_trade_date": None}
        last_trade_date = frame.index.max()
        return {
            "rows": int(len(frame.index)),
            "last_trade_date": (
                last_trade_date.date().isoformat() if hasattr(last_trade_date, "date") else str(last_trade_date)
            ),
            "columns": sorted(str(column) for column in frame.columns),
        }

    def _merge_trace_stage(
        self,
        trace: MarketMonitorTraceLogger,
        stage_name: str,
        payload: dict[str, Any],
    ) -> None:
        existing = trace.payload.get(stage_name)
        stage_payload = dict(existing) if isinstance(existing, dict) else {}
        stage_payload.update(payload)
        trace.set_stage(stage_name, stage_payload)

    def _save_dataset_cache(
        self,
        as_of_date: date,
        dataset: dict[str, dict[str, pd.DataFrame]],
        universe: dict[str, list[str]],
    ) -> None:
        if not self._is_dataset_cacheable(dataset):
            return
        self._dataset_cache[as_of_date] = {
            "dataset": dataset,
            "cached_at": datetime.now(),
            "symbol_cache_mtime": latest_symbol_cache_mtime(universe["all_symbols"]),
        }

    def _is_dataset_cacheable(self, dataset: dict[str, dict[str, pd.DataFrame]]) -> bool:
        core_data = dataset.get("core", {})
        return not self._missing_required_symbols(core_data)

    def _is_dataset_cache_usable(
        self,
        cache_entry: dict[str, Any],
        as_of_date: date,
        universe: dict[str, list[str]],
    ) -> bool:
        dataset = cache_entry.get("dataset")
        cached_at = cache_entry.get("cached_at")
        if dataset is None or cached_at is None:
            return False
        if not self._is_dataset_cacheable(dataset):
            return False
        if not self._is_live_market_date(as_of_date):
            return True
        age = (datetime.now() - cached_at).total_seconds()
        if age > self._LIVE_CACHE_TTL_SECONDS:
            return False
        latest_mtime = latest_symbol_cache_mtime(universe["all_symbols"])
        cached_mtime = cache_entry.get("symbol_cache_mtime")
        if latest_mtime and (cached_mtime is None or latest_mtime > cached_mtime):
            return False
        return True

    def _is_snapshot_cache_usable(
        self,
        payload: dict[str, Any],
        as_of_date: date,
        universe: dict[str, list[str]],
    ) -> bool:
        try:
            snapshot = MarketMonitorSnapshotResponse.model_validate(payload)
        except Exception:
            return False
        if not self._is_snapshot_cacheable(snapshot):
            return False
        if snapshot.as_of_date != as_of_date:
            return False
        if not self._is_live_market_date(as_of_date):
            return True
        age = (datetime.now() - snapshot.timestamp).total_seconds()
        if age > self._LIVE_CACHE_TTL_SECONDS:
            return False
        latest_mtime = latest_symbol_cache_mtime(universe["all_symbols"])
        return latest_mtime is None or latest_mtime <= snapshot.timestamp

    def _is_snapshot_cacheable(self, snapshot: MarketMonitorSnapshotResponse) -> bool:
        return (
            snapshot.model_overlay.status != "error"
            and snapshot.rule_snapshot.ready
            and not snapshot.rule_snapshot.missing_inputs
            and snapshot.final_execution_card is not None
        )

    def _is_live_market_date(self, as_of_date: date) -> bool:
        today = date.today()
        return as_of_date == today and _expected_market_close_date(as_of_date).date() == today

    def _build_rule_snapshot(
        self,
        dataset: dict[str, dict[str, pd.DataFrame]],
        universe: dict[str, list[str]],
    ) -> MarketMonitorRuleSnapshot:
        core_data = dataset["core"]
        missing_required = self._missing_required_symbols(core_data)
        source_coverage = self._build_source_coverage(core_data, universe["market_proxies"], missing_required)
        base_event_risk_flag = self._build_base_event_risk_flag()

        if missing_required:
            return MarketMonitorRuleSnapshot(
                ready=False,
                base_event_risk_flag=base_event_risk_flag,
                source_coverage=source_coverage,
                missing_inputs=missing_required,
                degraded_factors=source_coverage.degraded_factors,
                key_indicators={},
            )

        breadth_ratio = build_breadth_ratio(core_data, universe["market_proxies"])
        sector_data = {symbol: core_data[symbol] for symbol in universe["sector_etfs"] if symbol in core_data}
        long_term = summarize_score(build_long_term_series(core_data, breadth_ratio), LONG_TERM_ZONES)
        short_term = summarize_score(build_short_term_series(core_data, sector_data, breadth_ratio), SHORT_TERM_ZONES)
        system_risk = summarize_score(build_system_risk_series(core_data, breadth_ratio), SYSTEM_RISK_ZONES)
        style_effectiveness = self._build_style_effectiveness(core_data, universe["market_proxies"])
        base_execution_card = self._build_execution_card(
            long_term["score"],
            short_term["score"],
            system_risk["score"],
            base_event_risk_flag,
            style_effectiveness,
        )
        panic_card = self._build_panic_card(short_term["score"], system_risk["score"])
        key_indicators = self._build_key_indicators(core_data, breadth_ratio)

        return MarketMonitorRuleSnapshot(
            ready=True,
            long_term_score=MarketScoreCard(
                score=long_term["score"],
                zone=long_term["zone"],
                delta_1d=long_term["delta_1d"],
                delta_5d=long_term["delta_5d"],
                slope_state=long_term["slope_state"],
                action=self._long_term_action(long_term["score"]),
            ),
            short_term_score=MarketScoreCard(
                score=short_term["score"],
                zone=short_term["zone"],
                delta_1d=short_term["delta_1d"],
                delta_5d=short_term["delta_5d"],
                slope_state=short_term["slope_state"],
                action=self._short_term_action(short_term["score"]),
            ),
            system_risk_score=MarketScoreCard(
                score=system_risk["score"],
                zone=system_risk["zone"],
                delta_1d=system_risk["delta_1d"],
                delta_5d=system_risk["delta_5d"],
                slope_state=system_risk["slope_state"],
                action=self._system_risk_action(system_risk["score"]),
            ),
            style_effectiveness=style_effectiveness,
            panic_reversal_score=panic_card,
            base_regime_label=base_execution_card.regime_label,
            base_execution_card=base_execution_card,
            base_event_risk_flag=base_event_risk_flag,
            source_coverage=source_coverage,
            missing_inputs=[],
            degraded_factors=source_coverage.degraded_factors,
            key_indicators=key_indicators,
        )

    def _missing_required_symbols(self, core_data: dict[str, pd.DataFrame]) -> list[str]:
        required_symbols = ["SPY", "QQQ", "IWM"]
        return [symbol for symbol in required_symbols if core_data.get(symbol) is None or core_data[symbol].empty]

    def _build_source_coverage(
        self,
        core_data: dict[str, pd.DataFrame],
        proxy_symbols: list[str],
        missing_required: list[str],
    ) -> MarketSourceCoverage:
        available_core = sorted(symbol for symbol, frame in core_data.items() if frame is not None and not frame.empty)
        proxy_available = sum(
            1
            for symbol in proxy_symbols
            if core_data.get(symbol) is not None and not core_data[symbol].empty
        )
        degraded_factors = []
        notes = [
            f"实时 Yahoo Finance 日线已完成，共覆盖 {len(available_core)} 个核心/行业符号。",
            f"ETF/指数广度代理覆盖 {proxy_available}/{len(proxy_symbols)} 个符号。",
            "当前确定性评分卡使用 ETF/指数代理广度，而不是完整的纳斯达克 100 成分股扫描。",
        ]
        if missing_required:
            degraded_factors.append(f"missing_required_symbols:{','.join(missing_required)}")
            notes.append("核心市场符号不完整，因此未生成规则评分卡。")
        degraded_factors.extend(
            [
                "intraday_panic_confirmation_missing",
                "put_call_ratio_missing",
                "vix_term_structure_missing",
                "calendar_events_missing",
            ]
        )
        status = "degraded" if missing_required else "partial"
        return MarketSourceCoverage(
            status=status,
            data_freshness="live_request_yfinance_daily",
            degraded_factors=degraded_factors,
            notes=notes,
        )

    def _build_base_event_risk_flag(self) -> MarketEventRiskFlag:
        return MarketEventRiskFlag(
            index_level=MarketIndexEventRisk(active=False),
            stock_level=MarketStockEventRisk(
                earnings_stocks=[],
                rule="当前尚未接入事件日历数据源；模型叠加可能补充事件风险背景。",
            ),
        )

    def _build_style_effectiveness(
        self,
        core_data: dict[str, pd.DataFrame],
        proxy_symbols: list[str],
    ) -> MarketStyleEffectiveness:
        tactic_scores = score_tactic_layer(core_data, proxy_symbols)
        asset_scores = score_asset_layer(core_data)

        top_tactic = max(tactic_scores, key=tactic_scores.get)
        avoid_tactic = min(tactic_scores, key=tactic_scores.get)
        preferred_assets = sorted(asset_scores, key=asset_scores.get, reverse=True)[:2]
        avoid_assets = sorted(asset_scores, key=asset_scores.get)[:2]

        label_map = {
            "trend_breakout": "trend_breakout",
            "dip_buy": "dip_buy",
            "oversold_bounce": "oversold_bounce",
            "large_cap_tech": "large_cap_tech",
            "small_cap_momentum": "small_cap_momentum",
            "defensive": "defensive",
            "energy_cyclical": "energy_cyclical",
            "financials": "financials",
        }

        return MarketStyleEffectiveness(
            tactic_layer=MarketStyleTacticLayer(
                trend_breakout=MarketStyleSignal(
                    score=tactic_scores["trend_breakout"],
                    valid=tactic_scores["trend_breakout"] >= 55,
                    delta_5d=0,
                ),
                dip_buy=MarketStyleSignal(
                    score=tactic_scores["dip_buy"],
                    valid=tactic_scores["dip_buy"] >= 55,
                    delta_5d=0,
                ),
                oversold_bounce=MarketStyleSignal(
                    score=tactic_scores["oversold_bounce"],
                    valid=tactic_scores["oversold_bounce"] >= 55,
                    delta_5d=0,
                ),
                top_tactic=label_map[top_tactic],
                avoid_tactic=label_map[avoid_tactic],
            ),
            asset_layer=MarketStyleAssetLayer(
                large_cap_tech=MarketStyleSignal(
                    score=asset_scores["large_cap_tech"],
                    preferred="large_cap_tech" in preferred_assets,
                    delta_5d=0,
                ),
                small_cap_momentum=MarketStyleSignal(
                    score=asset_scores["small_cap_momentum"],
                    preferred="small_cap_momentum" in preferred_assets,
                    delta_5d=0,
                ),
                defensive=MarketStyleSignal(
                    score=asset_scores["defensive"],
                    preferred="defensive" in preferred_assets,
                    delta_5d=0,
                ),
                energy_cyclical=MarketStyleSignal(
                    score=asset_scores["energy_cyclical"],
                    preferred="energy_cyclical" in preferred_assets,
                    delta_5d=0,
                ),
                financials=MarketStyleSignal(
                    score=asset_scores["financials"],
                    preferred="financials" in preferred_assets,
                    delta_5d=0,
                ),
                preferred_assets=[label_map[item] for item in preferred_assets],
                avoid_assets=[label_map[item] for item in avoid_assets],
            ),
        )

    def _build_execution_card(
        self,
        long_score: float,
        short_score: float,
        system_risk_score: float,
        event_risk_flag: MarketEventRiskFlag,
        style_effectiveness: MarketStyleEffectiveness,
    ) -> MarketExecutionCard:
        regime_label = self._regime_label(long_score, short_score, system_risk_score)
        return self._build_execution_card_for_regime(regime_label, event_risk_flag, style_effectiveness)

    def _build_execution_card_for_regime(
        self,
        regime_label: str,
        event_risk_flag: MarketEventRiskFlag,
        style_effectiveness: MarketStyleEffectiveness,
    ) -> MarketExecutionCard:
        defaults = self._execution_defaults_for_regime(regime_label)
        return MarketExecutionCard(
            regime_label=regime_label,
            conflict_mode=defaults["conflict_mode"],
            total_exposure_range=defaults["total_exposure_range"],
            new_position_allowed=defaults["new_position_allowed"],
            chase_breakout_allowed=defaults["chase_breakout_allowed"],
            dip_buy_allowed=defaults["dip_buy_allowed"],
            overnight_allowed=defaults["overnight_allowed"],
            leverage_allowed=defaults["leverage_allowed"],
            single_position_cap=defaults["single_position_cap"],
            daily_risk_budget=defaults["daily_risk_budget"],
            tactic_preference=f"{style_effectiveness.tactic_layer.top_tactic}>{style_effectiveness.tactic_layer.avoid_tactic}",
            preferred_assets=style_effectiveness.asset_layer.preferred_assets,
            avoid_assets=style_effectiveness.asset_layer.avoid_assets,
            signal_confirmation=MarketExecutionSignalConfirmation(
                current_regime_days=1,
                downgrade_unlock_in_days=2,
                note="第 1 阶段暂未启用状态持续性确认逻辑。",
            ),
            event_risk_flag=event_risk_flag,
            summary=defaults["summary"],
        )

    def _execution_defaults_for_regime(self, regime_label: str) -> dict[str, Any]:
        if regime_label == "green":
            return {
                "total_exposure_range": "70%-90%",
                "conflict_mode": "trend_and_tape_aligned",
                "daily_risk_budget": "1.25R",
                "chase_breakout_allowed": True,
                "dip_buy_allowed": True,
                "new_position_allowed": True,
                "overnight_allowed": True,
                "leverage_allowed": True,
                "single_position_cap": "12%",
                "summary": "规则支持偏进攻型的趋势参与。",
            }
        elif regime_label == "yellow_green_swing":
            return {
                "total_exposure_range": "50%-70%",
                "conflict_mode": "swing_window_open",
                "daily_risk_budget": "1.0R",
                "chase_breakout_allowed": True,
                "dip_buy_allowed": True,
                "new_position_allowed": True,
                "overnight_allowed": True,
                "leverage_allowed": False,
                "single_position_cap": "12%",
                "summary": "规则更偏向主动波段交易，而非重仓趋势暴露。",
            }
        elif regime_label == "yellow":
            return {
                "total_exposure_range": "40%-60%",
                "conflict_mode": "conditional_offense",
                "daily_risk_budget": "0.9R",
                "chase_breakout_allowed": False,
                "dip_buy_allowed": True,
                "new_position_allowed": True,
                "overnight_allowed": True,
                "leverage_allowed": False,
                "single_position_cap": "10%",
                "summary": "规则允许在确认后择机进攻。",
            }
        elif regime_label == "orange":
            return {
                "total_exposure_range": "25%-45%",
                "conflict_mode": "defense_first",
                "daily_risk_budget": "0.75R",
                "chase_breakout_allowed": False,
                "dip_buy_allowed": True,
                "new_position_allowed": True,
                "overnight_allowed": True,
                "leverage_allowed": False,
                "single_position_cap": "8%",
                "summary": "规则偏向缩小仓位并保持防守姿态。",
            }
        return {
            "total_exposure_range": "0%-20%",
            "conflict_mode": "capital_protection",
            "daily_risk_budget": "0.25R",
            "chase_breakout_allowed": False,
            "dip_buy_allowed": False,
            "new_position_allowed": False,
            "overnight_allowed": False,
            "leverage_allowed": False,
            "single_position_cap": "5%",
            "summary": "规则优先保护本金。",
        }

    def _build_panic_card(self, short_score: float, system_risk_score: float) -> MarketPanicReversalCard:
        panic_gate = short_score < 35 and system_risk_score >= 45
        early_gate = short_score < 25 and system_risk_score >= 60

        if not panic_gate:
            panic_extreme = 25.0
            selling_exhaustion = 20.0
            intraday_reversal = 15.0
            followthrough = 15.0
            score = 25.0
            state = "none"
            zone = "inactive"
            action = "当前没有激活的恐慌反转交易形态。"
        else:
            panic_extreme = max(35.0, min(100.0, 65 + (35 - short_score) * 0.9 + (system_risk_score - 45) * 0.7))
            selling_exhaustion = max(25.0, min(100.0, 25 + (system_risk_score - short_score) * 0.45))
            intraday_reversal = max(20.0, min(100.0, 15 + (35 - short_score) * 1.1))
            followthrough = max(20.0, min(100.0, 15 + (35 - short_score) * 0.8 + max(0.0, system_risk_score - 55) * 0.2))
            score = panic_extreme * 0.4 + selling_exhaustion * 0.3 + max(intraday_reversal, followthrough) * 0.3
            if panic_extreme >= 80 or score >= 50:
                state = "confirmed"
                zone = "actionable"
                action = "规则引擎识别到可交易的恐慌反转形态，但当前确认仍限于日线级别。"
            else:
                state = "watch"
                zone = "watch"
                action = "规则引擎识别到恐慌条件，但确认仍不完整。"

        return MarketPanicReversalCard(
            score=round(score, 1),
            zone=zone,
            state=state,
            panic_extreme_score=round(panic_extreme, 1),
            selling_exhaustion_score=round(selling_exhaustion, 1),
            intraday_reversal_score=round(intraday_reversal, 1),
            followthrough_confirmation_score=round(followthrough, 1),
            action=action,
            system_risk_override="当系统性风险极高时，恐慌反转仓位也应保持上限控制。",
            stop_loss="1.0 倍 ATR",
            profit_rule="1R 先止盈 50%，其余仓位以保本止损跟踪。",
            timeout_warning=False,
            days_held=0,
            early_entry_allowed=state == "confirmed" and early_gate and intraday_reversal >= 60,
        )

    def _build_key_indicators(self, core_data: dict[str, pd.DataFrame], breadth_ratio: pd.Series) -> dict[str, Any]:
        spy_close = self._last_value(core_data["SPY"], "Close")
        qqq_close = self._last_value(core_data["QQQ"], "Close")
        iwm_close = self._last_value(core_data["IWM"], "Close")
        vix_close = self._last_value(core_data.get("^VIX", pd.DataFrame()), "Close")
        breadth = float(breadth_ratio.dropna().iloc[-1]) if not breadth_ratio.dropna().empty else None
        return {
            "spy_close": spy_close,
            "qqq_close": qqq_close,
            "iwm_close": iwm_close,
            "vix_close": vix_close,
            "breadth_above_200dma_pct": breadth,
        }

    def _last_value(self, frame: pd.DataFrame, column: str) -> float | None:
        series = frame.get(column)
        if series is None:
            return None
        clean = series.dropna()
        if clean.empty:
            return None
        return float(clean.iloc[-1])

    def _build_context_queries(self, rule_snapshot: MarketMonitorRuleSnapshot) -> list[str]:
        queries = [
            "What macro events are most relevant to US equities today or in the next 3 trading days?",
            "Are there any major earnings, policy, geopolitical, or regulatory events affecting SPY, QQQ, IWM, or mega-cap tech today?",
        ]
        if rule_snapshot.degraded_factors:
            queries.append(
                "Do recent sources explain elevated market risk or degraded breadth conditions for US equities?"
            )
        if rule_snapshot.base_regime_label in {"orange", "red"}:
            queries.append(
                "Are there current catalysts that justify a defensive or risk-off stance in US equities?"
            )
        if rule_snapshot.base_regime_label == "yellow_green_swing":
            queries.append(
                "Is there evidence of sector rotation or short-term swing conditions in US equities right now?"
            )
        return queries

    def _merge_overlay(
        self,
        rule_snapshot: MarketMonitorRuleSnapshot,
        model_overlay: MarketMonitorModelOverlay,
    ) -> MarketExecutionCard | None:
        base_event_risk_flag = rule_snapshot.base_event_risk_flag
        final_event_risk_flag = model_overlay.event_risk_override or base_event_risk_flag
        if not rule_snapshot.base_execution_card:
            return None

        adjustments = model_overlay.execution_adjustments
        target_regime = (
            adjustments.regime_label
            if adjustments and adjustments.regime_label
            else model_overlay.regime_override or rule_snapshot.base_execution_card.regime_label
        )
        rebuilt_card = self._build_execution_card_for_regime(
            target_regime,
            final_event_risk_flag,
            rule_snapshot.style_effectiveness,
        )
        payload = deepcopy(rebuilt_card.model_dump(mode="python"))
        if adjustments:
            for field, value in adjustments.model_dump(exclude_none=True).items():
                payload[field] = value
        payload["event_risk_flag"] = final_event_risk_flag.model_dump(mode="python")
        return MarketExecutionCard.model_validate(payload)

    def _regime_label(self, long_score: float, short_score: float, system_risk_score: float) -> str:
        if system_risk_score > 70 or long_score < 35:
            return "red"
        if 45 <= long_score < 65 and short_score >= 60 and system_risk_score <= 35:
            return "yellow_green_swing"
        if long_score >= 65 and short_score >= 55 and system_risk_score <= 35:
            return "green"
        if long_score >= 50 and short_score >= 45 and system_risk_score <= 50:
            return "yellow"
        return "orange"

    def _long_term_action(self, score: float) -> str:
        if score >= 80:
            return "长期环境强劲，适合提高趋势仓位。"
        if score >= 65:
            return "中期趋势健康，可以择机增加风险暴露。"
        if score >= 50:
            return "中期趋势偏积极，但尚未完全确认。"
        if score >= 35:
            return "长期环境偏谨慎，仓位应保持中等。"
        return "长期环境偏防守，应避免过重的趋势风险。"

    def _short_term_action(self, score: float) -> str:
        if score >= 80:
            return "短线条件非常活跃，具备较高交易性。"
        if score >= 65:
            return "短线盘面活跃，但应提升筛选标准，避免鲁莽追价。"
        if score >= 50:
            return "短线条件可操作，适合低吸和确认后的突破。"
        if score >= 35:
            return "短线环境更适合观察，而非激进进攻。"
        return "短线环境偏弱，应避免追价和隔夜波动暴露。"

    def _system_risk_action(self, score: float) -> str:
        if score >= 80:
            return "系统性风险显著升高，应优先保护本金。"
        if score >= 60:
            return "风险压力较高，应降低总暴露并避免杠杆。"
        if score >= 45:
            return "风险有所抬升，应收紧风险预算并减少追价。"
        if score >= 20:
            return "系统风险处于常态，可使用标准风控。"
        return "系统风险相对近期区间较温和。"
