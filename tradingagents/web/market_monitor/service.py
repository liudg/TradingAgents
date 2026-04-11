from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .assessment import MarketMonitorAssessmentService
from .cache import latest_symbol_cache_mtime, load_snapshot_cache, save_snapshot_cache
from .context import MarketMonitorContextPayload
from .data import _expected_market_close_date, build_market_dataset
from .metrics import build_market_snapshot
from .schemas import (
    MarketDataSnapshot,
    MarketHistoryPoint,
    MarketMissingDataItem,
    MarketMonitorDataStatusResponse,
    MarketMonitorHistoryResponse,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
    MarketMonitorTraceDetail,
    MarketMonitorTraceLogEntry,
    MarketMonitorTraceSummary,
)
from .trace import MarketMonitorTraceLogger, MarketMonitorTraceStore
from .universe import get_market_monitor_universe


class MarketMonitorService:
    _LIVE_CACHE_TTL_SECONDS = 300

    def __init__(self, trace_root: Path | None = None) -> None:
        self._assessment_service = MarketMonitorAssessmentService()
        self._dataset_cache: dict[date, dict[str, Any]] = {}
        self._trace_store = MarketMonitorTraceStore(trace_root)

    def get_snapshot(self, request: MarketMonitorSnapshotRequest) -> MarketMonitorSnapshotResponse:
        as_of_date = request.as_of_date or date.today()
        universe = get_market_monitor_universe()
        trace = self._trace_store.create_logger(as_of_date, request.force_refresh)
        trace.log_event("Request", f"市场监控快照请求开始：{as_of_date.isoformat()}（force_refresh={request.force_refresh}）")
        trace.set_stage(
            "request",
            {"as_of_date": as_of_date.isoformat(), "force_refresh": request.force_refresh},
        )

        try:
            if not request.force_refresh:
                cached_snapshot = load_snapshot_cache(as_of_date)
                if cached_snapshot is not None and self._is_snapshot_cache_usable(cached_snapshot, as_of_date, universe):
                    snapshot = MarketMonitorSnapshotResponse.model_validate(cached_snapshot)
                    snapshot.trace_id = trace.trace_id
                    trace.set_stage("cache_decision", {"snapshot_cache_hit": True, "dataset_cache_hit": False})
                    trace.set_stage(
                        "assessment_summary",
                        {
                            "overall_confidence": snapshot.overall_confidence,
                            "long_term_label": snapshot.assessment.long_term_card.label,
                            "execution_label": snapshot.assessment.execution_card.label,
                            "evidence_source_count": len(snapshot.evidence_sources),
                        },
                    )
                    trace.set_summary_fields(
                        overall_confidence=snapshot.overall_confidence,
                        long_term_label=snapshot.assessment.long_term_card.label,
                        execution_label=snapshot.assessment.execution_card.label,
                    )
                    trace.log_event("Response", "返回缓存快照")
                    trace.complete({"served_from_snapshot_cache": True, "trace_id": trace.trace_id})
                    return snapshot

            dataset, dataset_meta = self._get_dataset(universe, as_of_date, force_refresh=request.force_refresh, trace=trace)
            trace.set_stage("dataset_summary", dataset_meta)

            core_data = dataset["core"]
            local_market_data, derived_metrics = build_market_snapshot(core_data, universe["market_proxies"])
            missing_data = self._build_missing_data(core_data)
            market_data_snapshot = MarketDataSnapshot(
                local_market_data=local_market_data,
                derived_metrics=derived_metrics,
                llm_reasoning_notes=[],
            )
            context = MarketMonitorContextPayload(
                as_of_date=as_of_date.isoformat(),
                market_data_snapshot=market_data_snapshot,
                missing_data=missing_data,
                instructions=self._build_instructions(),
            )
            trace.set_stage(
                "context_summary",
                {
                    "local_symbol_count": len(local_market_data),
                    "derived_metric_keys": sorted(derived_metrics.keys()),
                    "missing_data_keys": [item.key for item in missing_data],
                },
            )
            trace.log_event("Context", f"已组装上下文：{len(local_market_data)} 个本地符号，{len(missing_data)} 个缺失项")

            assessment, evidence_sources, llm_reasoning_notes, overall_confidence = self._assessment_service.create_assessment(
                context
            )
            market_data_snapshot.llm_reasoning_notes = llm_reasoning_notes
            trace.set_stage(
                "assessment_summary",
                {
                    "overall_confidence": overall_confidence,
                    "long_term_label": assessment.long_term_card.label,
                    "execution_label": assessment.execution_card.label,
                    "evidence_sources": evidence_sources,
                },
            )
            trace.set_summary_fields(
                overall_confidence=overall_confidence,
                long_term_label=assessment.long_term_card.label,
                execution_label=assessment.execution_card.label,
            )
            trace.log_event("Assessment", f"LLM 裁决完成：长线={assessment.long_term_card.label}，执行={assessment.execution_card.label}")

            response = MarketMonitorSnapshotResponse(
                timestamp=datetime.now(),
                as_of_date=as_of_date,
                trace_id=trace.trace_id,
                market_data_snapshot=market_data_snapshot,
                missing_data=missing_data,
                assessment=assessment,
                evidence_sources=evidence_sources,
                overall_confidence=overall_confidence,
            )
            save_snapshot_cache(as_of_date, response.model_dump(mode="json"))
            trace.log_event("Cache", "已写入快照缓存")
            trace.log_event("Response", "市场监控快照请求完成")
            trace.complete({"served_from_snapshot_cache": False, "trace_id": trace.trace_id})
            return response
        except Exception as exc:
            trace.log_event("Error", f"{exc.__class__.__name__}: {exc}")
            trace.fail("snapshot", exc)
            raise

    def get_history(self, as_of_date: date, days: int = 10) -> MarketMonitorHistoryResponse:
        points: list[MarketHistoryPoint] = []
        for offset in range(max(days, 1)):
            target = as_of_date - timedelta(days=offset)
            cached_snapshot = load_snapshot_cache(target)
            if not cached_snapshot:
                continue
            try:
                snapshot = MarketMonitorSnapshotResponse.model_validate(cached_snapshot)
            except Exception:
                continue
            points.append(
                MarketHistoryPoint(
                    trade_date=snapshot.as_of_date,
                    long_term_label=snapshot.assessment.long_term_card.label,
                    short_term_label=snapshot.assessment.short_term_card.label,
                    system_risk_label=snapshot.assessment.system_risk_card.label,
                    execution_label=snapshot.assessment.execution_card.label,
                    overall_confidence=snapshot.overall_confidence,
                )
            )
        points.sort(key=lambda item: item.trade_date, reverse=True)
        return MarketMonitorHistoryResponse(as_of_date=as_of_date, points=points)

    def get_data_status(self, as_of_date: date) -> MarketMonitorDataStatusResponse:
        universe = get_market_monitor_universe()
        dataset, _ = self._get_dataset(universe, as_of_date)
        core_data = dataset["core"]
        available_local_data = sorted(symbol for symbol, frame in core_data.items() if frame is not None and not frame.empty)
        return MarketMonitorDataStatusResponse(
            as_of_date=as_of_date,
            available_local_data=available_local_data,
            missing_data=self._build_missing_data(core_data),
            search_enabled=True,
            latest_cache_status={
                "latest_symbol_cache_mtime": (
                    latest_symbol_cache_mtime(universe["all_symbols"]).isoformat()
                    if latest_symbol_cache_mtime(universe["all_symbols"])
                    else None
                )
            },
        )

    def list_traces(self, as_of_date: date | None = None, status: str | None = None, limit: int = 20) -> list[MarketMonitorTraceSummary]:
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
                trace.set_stage("cache_decision", {"snapshot_cache_hit": False, "dataset_cache_hit": False, "reason": "force_refresh"})
            return dataset, meta

        cached_entry = self._dataset_cache.get(as_of_date)
        if cached_entry is not None and self._is_dataset_cache_usable(cached_entry, as_of_date, universe):
            dataset = cached_entry["dataset"]
            meta = self._build_dataset_summary(dataset, universe, "memory_cache")
            if trace is not None:
                trace.set_stage("cache_decision", {"snapshot_cache_hit": False, "dataset_cache_hit": True})
            return dataset, meta

        dataset = build_market_dataset(universe, as_of_date, force_refresh=False)
        self._save_dataset_cache(as_of_date, dataset, universe)
        meta = self._build_dataset_summary(dataset, universe, "live_request")
        if trace is not None:
            trace.set_stage("cache_decision", {"snapshot_cache_hit": False, "dataset_cache_hit": False})
        return dataset, meta

    def _build_dataset_summary(
        self, dataset: dict[str, dict[str, pd.DataFrame]], universe: dict[str, list[str]], source: str
    ) -> dict[str, Any]:
        core_data = dataset.get("core", {})
        available_symbols = sorted(symbol for symbol, frame in core_data.items() if frame is not None and not frame.empty)
        return {
            "source": source,
            "available_symbol_count": len(available_symbols),
            "available_symbols_sample": available_symbols[:12],
            "market_proxy_count": len(universe["market_proxies"]),
        }

    def _build_missing_data(self, core_data: dict[str, pd.DataFrame]) -> list[MarketMissingDataItem]:
        missing: list[MarketMissingDataItem] = []
        required_symbols = ["SPY", "QQQ", "IWM", "^VIX"]
        for symbol in required_symbols:
            frame = core_data.get(symbol)
            if frame is None or frame.empty:
                missing.append(
                    MarketMissingDataItem(
                        key=f"missing_symbol_{symbol}",
                        label=f"缺少 {symbol} 日线",
                        required_for=["long_term_card", "short_term_card", "system_risk_card"],
                        status="missing",
                        note=f"本地未获取到 {symbol} 日线数据。",
                    )
                )

        missing.extend(
            [
                MarketMissingDataItem(
                    key="vix_term_structure",
                    label="VIX 期限结构",
                    required_for=["long_term_card", "system_risk_card"],
                    status="missing",
                    note="本地未接入 VIX3M/VIX 时序数据。",
                ),
                MarketMissingDataItem(
                    key="market_breadth_ad_line",
                    label="NYSE A/D 线",
                    required_for=["long_term_card"],
                    status="missing",
                    note="本地未接入交易所级 advance/decline 数据。",
                ),
                MarketMissingDataItem(
                    key="calendar_events",
                    label="事件日历",
                    required_for=["event_risk_card", "execution_card"],
                    status="missing",
                    note="本地未接入宏观与财报事件日历。",
                ),
                MarketMissingDataItem(
                    key="stock_level_rs_leadership",
                    label="股票级 RS 龙头确认",
                    required_for=["long_term_card"],
                    status="missing",
                    note="当前仅有 ETF/指数代理池，没有完整股票横截面。",
                ),
            ]
        )
        return missing

    def _build_instructions(self) -> dict[str, Any]:
        return {
            "goal": "基于本地市场数据和外部搜索，对美国股市当前环境给出结构化裁决。",
            "card_definitions": {
                "long_term_card": "判断中期环境偏多、偏空或中性，以及是否支持趋势仓位。",
                "short_term_card": "判断短线交易环境是否友好。",
                "system_risk_card": "判断系统性风险是否抬升。",
                "execution_card": "输出总仓位、追高、低吸、隔夜、杠杆与风险预算建议。",
                "event_risk_card": "识别未来三日对指数或主要风格有影响的事件风险。",
                "panic_card": "判断是否存在恐慌反转型机会。",
            },
        }

    def _save_dataset_cache(
        self,
        as_of_date: date,
        dataset: dict[str, dict[str, pd.DataFrame]],
        universe: dict[str, list[str]],
    ) -> None:
        self._dataset_cache[as_of_date] = {
            "dataset": dataset,
            "latest_symbol_cache_mtime": latest_symbol_cache_mtime(universe["all_symbols"]),
        }

    def _is_dataset_cache_usable(
        self,
        cached_entry: dict[str, Any],
        as_of_date: date,
        universe: dict[str, list[str]],
    ) -> bool:
        dataset = cached_entry.get("dataset")
        if not isinstance(dataset, dict):
            return False
        if latest_symbol_cache_mtime(universe["all_symbols"]) != cached_entry.get("latest_symbol_cache_mtime"):
            return False
        core = dataset.get("core", {})
        spy_frame = core.get("SPY")
        if spy_frame is None or spy_frame.empty:
            return False
        if spy_frame.index.max() < _expected_market_close_date(as_of_date):
            return False
        return True

    def _is_snapshot_cache_usable(
        self,
        cached_snapshot: dict[str, Any],
        as_of_date: date,
        universe: dict[str, list[str]],
    ) -> bool:
        try:
            snapshot = MarketMonitorSnapshotResponse.model_validate(cached_snapshot)
        except Exception:
            return False
        if snapshot.as_of_date != as_of_date:
            return False
        latest_mtime = latest_symbol_cache_mtime(universe["all_symbols"])
        if latest_mtime is None:
            return True
        return snapshot.timestamp >= latest_mtime
