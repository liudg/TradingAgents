from __future__ import annotations

from concurrent.futures import Executor, ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .data import build_market_dataset
from .errors import MarketMonitorError
from .llm import MarketMonitorLlmGateway
from .metrics import build_market_snapshot
from .prompt_store import PromptCaptureStore
from .run_store import MonitorRunStore
from .schemas import (
    EvidenceReferenceItem,
    ExecutionDecisionPack,
    JudgmentCard,
    MarketFactItem,
    MarketFactSheet,
    MarketInputBundle,
    MarketJudgmentPack,
    MarketMonitorPromptDetail,
    MarketMonitorPromptSummary,
    MarketMonitorRunCreateRequest,
    MarketMonitorRunCreateResponse,
    MarketMonitorRunDetail,
    MarketMonitorRunEvidenceResponse,
    MarketMonitorRunLogEntry,
    MarketMonitorRunResultSummary,
    MarketMonitorRunStageDetail,
    MarketMonitorRunStagesResponse,
    SearchEvidenceItem,
    SEARCH_SLOT_KEYS,
    STAGE_KEYS,
    SearchSlotPack,
)
from .universe import get_market_monitor_universe


class MarketMonitorService:
    def __init__(
        self,
        run_root: Path | None = None,
        prompt_root: Path | None = None,
        run_executor: Executor | None = None,
    ) -> None:
        self._run_store = MonitorRunStore(run_root)
        self._prompt_store = PromptCaptureStore(prompt_root, run_store=self._run_store)
        self._llm = MarketMonitorLlmGateway(self._prompt_store)
        self._owns_executor = run_executor is None
        self._run_executor = run_executor or ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="market-monitor",
        )
        self._recover_abandoned_runs()

    def shutdown(self, wait: bool = False) -> None:
        if self._owns_executor:
            self._run_executor.shutdown(wait=wait)

    def create_run(self, request: MarketMonitorRunCreateRequest) -> MarketMonitorRunCreateResponse:
        as_of_date = request.as_of_date or date.today()
        run = self._run_store.create_run(as_of_date)
        self._run_store.append_log(run.run_id, "Request", f"启动市场监控运行：{as_of_date.isoformat()}")
        try:
            self._run_executor.submit(
                self._execute_run_pipeline,
                run.run_id,
                as_of_date,
                request.force_refresh,
            )
        except Exception as exc:
            detail = self._run_store.get_run(run.run_id).model_copy(
                update={
                    "status": "failed",
                    "current_stage": "failed",
                    "finished_at": datetime.now(timezone.utc),
                    "error_message": str(exc),
                }
            )
            self._run_store.save_run(detail)
            self._run_store.append_log(run.run_id, "Error", f"{exc.__class__.__name__}: {exc}")
            raise
        return MarketMonitorRunCreateResponse(run_id=run.run_id, status="running")

    def _execute_run_pipeline(self, run_id: str, as_of_date: date, force_refresh: bool) -> None:
        stages = self._run_store.get_stages(run_id).stages
        try:
            input_bundle = self._run_input_bundle(run_id, as_of_date, force_refresh, stages)
            search_pack = self._collect_search_slots(run_id, input_bundle, stages)
            fact_sheet = self._build_fact_sheet(run_id, input_bundle, search_pack, stages)
            judgments = self._build_judgments(run_id, fact_sheet, stages)
            execution = self._build_execution(run_id, fact_sheet, judgments, stages)
            result = MarketMonitorRunResultSummary(
                long_term_label=judgments.long_term_card.label,
                system_risk_label=judgments.system_risk_card.label,
                short_term_label=judgments.short_term_card.label,
                event_risk_label=judgments.event_risk_card.label,
                panic_label=judgments.panic_card.label,
                execution_summary=execution.summary,
                execution=execution,
            )
            detail = self._run_store.get_run(run_id).model_copy(
                update={
                    "status": "completed",
                    "current_stage": "completed",
                    "finished_at": datetime.now(timezone.utc),
                    "result": result,
                }
            )
            self._run_store.save_run(detail)
            self._run_store.append_log(run_id, "Response", "市场监控运行完成")
        except Exception as exc:
            current_stage = self._run_store.get_run(run_id).current_stage
            if current_stage not in {"pending", "completed", "failed"}:
                self._set_stage(
                    stages,
                    run_id,
                    current_stage,
                    "failed",
                    error={
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                    },
                )
            detail = self._run_store.get_run(run_id).model_copy(
                update={
                    "status": "failed",
                    "current_stage": "failed",
                    "finished_at": datetime.now(timezone.utc),
                    "error_message": str(exc),
                }
            )
            self._run_store.save_run(detail)
            self._run_store.append_log(run_id, "Error", f"{exc.__class__.__name__}: {exc}")

    def get_run(self, run_id: str) -> MarketMonitorRunDetail:
        return self._run_store.get_run(run_id)

    def get_run_stages(self, run_id: str) -> MarketMonitorRunStagesResponse:
        run = self._run_store.get_run(run_id)
        stages_response = self._run_store.get_stages(run_id)
        return self._reconcile_stages_with_run(run, stages_response)

    def get_run_evidence(self, run_id: str) -> MarketMonitorRunEvidenceResponse:
        return self._run_store.get_evidence(run_id)

    def list_run_logs(self, run_id: str) -> list[MarketMonitorRunLogEntry]:
        self._run_store.get_run(run_id)
        return self._run_store.list_logs(run_id)

    def list_run_prompts(self, run_id: str) -> list[MarketMonitorPromptSummary]:
        self._run_store.get_run(run_id)
        return self._prompt_store.list_prompts(run_id)

    def get_prompt_detail(self, run_id: str, prompt_id: str) -> MarketMonitorPromptDetail:
        self._run_store.get_run(run_id)
        return self._prompt_store.get_prompt(run_id, prompt_id)

    def _recover_abandoned_runs(self) -> None:
        for run in self._run_store.list_runs():
            if run.status != "running":
                continue
            try:
                stages = self._run_store.get_stages(run.run_id).stages
                failed_stage_key = run.current_stage if run.current_stage not in {"pending", "completed", "failed"} else ""
                if not failed_stage_key and stages:
                    failed_stage_key = stages[0].stage_key
                if failed_stage_key:
                    self._set_stage(
                        stages,
                        run.run_id,
                        failed_stage_key,
                        "failed",
                        error={
                            "type": "AbandonedRun",
                            "message": "服务重启或后台任务中断，运行未能继续执行。",
                        },
                    )

                recovered = run.model_copy(
                    update={
                        "status": "failed",
                        "current_stage": "failed",
                        "finished_at": datetime.now(timezone.utc),
                        "error_message": "市场监控运行在服务重启或后台任务中断后未恢复，已标记为失败。",
                    }
                )
                self._run_store.save_run(recovered)
                self._run_store.append_log(
                    run.run_id,
                    "Recovery",
                    "检测到未完成的历史运行，已在服务启动时标记为失败。",
                )
            except Exception as exc:
                corrupted = run.model_copy(
                    update={
                        "status": "failed",
                        "current_stage": "failed",
                        "finished_at": datetime.now(timezone.utc),
                        "error_message": f"市场监控运行元数据损坏，恢复时失败：{exc}",
                    }
                )
                self._run_store.save_run(corrupted)
                self._run_store.append_log(
                    run.run_id,
                    "Recovery",
                    f"检测到损坏的历史运行元数据，已标记失败：{exc}",
                )

    def _run_input_bundle(
        self,
        run_id: str,
        as_of_date: date,
        force_refresh: bool,
        stages: list[MarketMonitorRunStageDetail],
    ) -> MarketInputBundle:
        self._set_stage(stages, run_id, "input_bundle", "running")
        universe = get_market_monitor_universe()
        dataset = build_market_dataset(universe, as_of_date, force_refresh=force_refresh)
        core_data = dataset["core"]
        local_market_data, derived_metrics = build_market_snapshot(core_data, universe["market_proxies"])
        available_local_data = sorted(local_market_data.keys())
        open_gaps = self._build_open_gaps(core_data)
        bundle = MarketInputBundle(
            as_of_date=as_of_date,
            generated_at=datetime.now(timezone.utc),
            local_market_data=local_market_data,
            derived_metrics=derived_metrics,
            available_local_data=available_local_data,
            open_gaps=open_gaps,
        )
        self._set_stage(
            stages,
            run_id,
            "input_bundle",
            "completed",
            {
                "available_local_data": available_local_data,
                "derived_metric_keys": sorted(derived_metrics.keys()),
                "open_gap_count": len(open_gaps),
            },
        )
        self._run_store.append_log(run_id, "InputBundle", f"完成本地输入摘要，覆盖 {len(available_local_data)} 个符号")
        return bundle

    def _collect_search_slots(
        self,
        run_id: str,
        input_bundle: MarketInputBundle,
        stages: list[MarketMonitorRunStageDetail],
    ) -> SearchSlotPack:
        self._set_stage(stages, run_id, "search_slots", "running")
        queries = self._build_slot_queries(input_bundle)
        slot_properties = {
            slot_key: {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["title", "summary", "source", "published_at"],
                    "properties": {
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "source": {"type": "string"},
                        "published_at": {"type": "string"},
                    },
                },
            }
            for slot_key in SEARCH_SLOT_KEYS
        }
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["slots"],
            "properties": {
                "slots": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": list(SEARCH_SLOT_KEYS),
                    "properties": slot_properties,
                }
            }
        }
        payload = self._llm.request_json(
            run_id=run_id,
            stage_key="search_slots",
            attempt=1,
            instructions=(
                "你是美国股市信息检索助手。"
                "只按给定槽位返回候选事实，不输出最终市场结论。"
                "必须覆盖所有给定槽位。"
                "即使某个槽位没有命中结果，也必须返回该槽位对应的空数组。"
                "不要新增未提供的槽位。"
            ),
            input_payload={
                "as_of_date": input_bundle.as_of_date.isoformat(),
                "queries": queries,
                "open_gaps": input_bundle.open_gaps,
            },
            schema=schema,
            tools=[
                {
                    "type": "web_search",
                    "search_context_size": "medium",
                    "user_location": {
                        "type": "approximate",
                        "country": "US",
                        "region": "California",
                        "timezone": "America/Los_Angeles",
                    },
                }
            ],
        )
        slots: dict[str, list[SearchEvidenceItem]] = {}
        if payload and isinstance(payload.get("slots"), dict):
            for slot_key, items in payload["slots"].items():
                if slot_key not in SEARCH_SLOT_KEYS:
                    raise MarketMonitorError(f"search_slots 阶段返回了未知槽位: {slot_key}")
                slots[slot_key] = [
                    SearchEvidenceItem(
                        slot_key=slot_key,
                        query=queries.get(slot_key),
                        title=str(item.get("title", "")),
                        summary=str(item.get("summary", "")),
                        source=str(item.get("source", "")),
                        published_at=str(item.get("published_at", "")) or None,
                        captured_at=datetime.now(timezone.utc),
                    )
                    for item in items[:3]
                ]
        search_pack = SearchSlotPack(slots=slots)
        self._set_stage(
            stages,
            run_id,
            "search_slots",
            "completed",
            {
                "slot_count": len(slots),
                "filled_slots": sorted(key for key, values in slots.items() if values),
            },
        )
        self._run_store.append_log(run_id, "Search", f"完成槽位搜索，命中 {sum(len(items) for items in slots.values())} 条候选结果")
        return search_pack

    def _build_fact_sheet(
        self,
        run_id: str,
        input_bundle: MarketInputBundle,
        search_pack: SearchSlotPack,
        stages: list[MarketMonitorRunStageDetail],
    ) -> MarketFactSheet:
        self._set_stage(stages, run_id, "fact_sheet", "running")
        observed_facts: list[MarketFactItem] = []
        filled_facts: list[MarketFactItem] = []
        evidence_index: dict[str, list[EvidenceReferenceItem]] = {}
        fact_confidence: dict[str, float] = {}

        for symbol, payload in input_bundle.local_market_data.items():
            fact_id = f"local_{symbol.lower()}_state"
            statement = (
                f"{symbol} 收盘 {payload.get('close')}，5 日变化 {payload.get('change_5d_pct')}%，"
                f"20 日变化 {payload.get('change_20d_pct')}%，站上 200 日均线={payload.get('above_ma200')}"
            )
            observed_facts.append(
                MarketFactItem(
                    fact_id=fact_id,
                    statement=statement,
                    source_type="local",
                    confidence=0.95,
                    evidence_refs=[],
                )
            )
            fact_confidence[fact_id] = 0.95

        for slot_key, items in search_pack.slots.items():
            for index, item in enumerate(items, start=1):
                fact_id = f"{slot_key}_{index}"
                filled_facts.append(
                    MarketFactItem(
                        fact_id=fact_id,
                        statement=item.summary or item.title,
                        source_type="search",
                        confidence=0.65,
                        evidence_refs=[fact_id],
                    )
                )
                fact_confidence[fact_id] = 0.65
                evidence_index[fact_id] = [
                    EvidenceReferenceItem(
                        slot_key=slot_key,
                        query=item.query,
                        title=item.title,
                        source=item.source,
                        published_at=item.published_at,
                    )
                ]

        fact_sheet = MarketFactSheet(
            observed_facts=observed_facts[:12],
            filled_facts=filled_facts[:12],
            open_gaps=input_bundle.open_gaps,
            evidence_index={
                k: [ref.model_dump(mode="json") for ref in refs]
                for k, refs in evidence_index.items()
            },
            fact_confidence=fact_confidence,
        )
        self._run_store.save_evidence(
            run_id,
            MarketMonitorRunEvidenceResponse(
                run_id=run_id,
                evidence_index=evidence_index,
                search_slots={
                    slot_key: [item.model_dump(mode="json") for item in items]
                    for slot_key, items in search_pack.slots.items()
                },
                open_gaps=input_bundle.open_gaps,
            ),
        )
        self._set_stage(
            stages,
            run_id,
            "fact_sheet",
            "completed",
            {
                "observed_fact_count": len(observed_facts),
                "filled_fact_count": len(filled_facts),
                "open_gap_count": len(input_bundle.open_gaps),
            },
        )
        self._run_store.append_log(run_id, "FactSheet", "事实整编完成")
        return fact_sheet

    def _build_judgments(
        self,
        run_id: str,
        fact_sheet: MarketFactSheet,
        stages: list[MarketMonitorRunStageDetail],
    ) -> MarketJudgmentPack:
        self._set_stage(stages, run_id, "judgment_group_a", "running")
        group_a = self._llm.request_json(
            run_id=run_id,
            stage_key="judgment_group_a",
            attempt=1,
            instructions="你负责长期环境与系统风险裁决。必须引用事实表中的事实，并承认不确定性。",
            input_payload=fact_sheet.model_dump(mode="json"),
            schema=self._judgment_schema(["long_term_card", "system_risk_card"]),
        )
        try:
            group_a_cards = {
                "long_term_card": JudgmentCard.model_validate(group_a["long_term_card"]),
                "system_risk_card": JudgmentCard.model_validate(group_a["system_risk_card"]),
            }
        except Exception as exc:
            raise MarketMonitorError(f"judgment_group_a 阶段模型输出结构无效: {exc}") from exc
        self._set_stage(
            stages,
            run_id,
            "judgment_group_a",
            "completed",
            {
                "long_term_label": group_a_cards["long_term_card"].label,
                "system_risk_label": group_a_cards["system_risk_card"].label,
            },
        )
        self._run_store.append_log(run_id, "JudgmentA", "完成长期环境与系统风险裁决")

        self._set_stage(stages, run_id, "judgment_group_b", "running")
        group_b = self._llm.request_json(
            run_id=run_id,
            stage_key="judgment_group_b",
            attempt=1,
            instructions="你负责短线环境、事件风险、恐慌模块裁决。必须引用事实表中的事实，并承认不确定性。",
            input_payload=fact_sheet.model_dump(mode="json"),
            schema=self._judgment_schema(["short_term_card", "event_risk_card", "panic_card"]),
        )
        try:
            group_b_cards = {
                "short_term_card": JudgmentCard.model_validate(group_b["short_term_card"]),
                "event_risk_card": JudgmentCard.model_validate(group_b["event_risk_card"]),
                "panic_card": JudgmentCard.model_validate(group_b["panic_card"]),
            }
        except Exception as exc:
            raise MarketMonitorError(f"judgment_group_b 阶段模型输出结构无效: {exc}") from exc
        self._set_stage(
            stages,
            run_id,
            "judgment_group_b",
            "completed",
            {
                "short_term_label": group_b_cards["short_term_card"].label,
                "event_risk_label": group_b_cards["event_risk_card"].label,
                "panic_label": group_b_cards["panic_card"].label,
            },
        )
        self._run_store.append_log(run_id, "JudgmentB", "完成短线、事件与恐慌裁决")

        return MarketJudgmentPack(
            long_term_card=group_a_cards["long_term_card"],
            system_risk_card=group_a_cards["system_risk_card"],
            short_term_card=group_b_cards["short_term_card"],
            event_risk_card=group_b_cards["event_risk_card"],
            panic_card=group_b_cards["panic_card"],
        )

    def _build_execution(
        self,
        run_id: str,
        fact_sheet: MarketFactSheet,
        judgments: MarketJudgmentPack,
        stages: list[MarketMonitorRunStageDetail],
    ) -> ExecutionDecisionPack:
        self._set_stage(stages, run_id, "execution_decision", "running")
        payload = self._llm.request_json(
            run_id=run_id,
            stage_key="execution_decision",
            attempt=1,
            instructions="你负责执行建议。可自由综合判断，但必须显式引用事实上游依据与风险权衡。",
            input_payload={
                "fact_sheet": fact_sheet.model_dump(mode="json"),
                "judgments": judgments.model_dump(mode="json"),
            },
            schema={
                "type": "object",
                "additionalProperties": False,
                "required": ["summary", "confidence", "decision_basis", "tradeoffs", "risk_flags", "actions"],
                "properties": {
                    "summary": {"type": "string"},
                    "confidence": {"type": "number"},
                    "decision_basis": {"type": "array", "items": {"type": "string"}},
                    "tradeoffs": {"type": "array", "items": {"type": "string"}},
                    "risk_flags": {"type": "array", "items": {"type": "string"}},
                    "actions": {"type": "array", "items": {"type": "string"}},
                },
            },
        )
        try:
            execution = ExecutionDecisionPack.model_validate(payload)
        except Exception as exc:
            raise MarketMonitorError(f"execution_decision 阶段模型输出结构无效: {exc}") from exc
        self._set_stage(
            stages,
            run_id,
            "execution_decision",
            "completed",
            {
                "summary": execution.summary,
                "confidence": execution.confidence,
            },
        )
        self._run_store.append_log(run_id, "Execution", "执行建议生成完成")
        return execution

    def _set_stage(
        self,
        stages: list[MarketMonitorRunStageDetail],
        run_id: str,
        stage_key: str,
        status: str,
        summary: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        next_stages: list[MarketMonitorRunStageDetail] = []
        for stage in stages:
            if stage.stage_key != stage_key:
                next_stages.append(stage)
                continue
            started_at = stage.started_at or now if status == "running" else stage.started_at
            finished_at = now if status in {"completed", "failed", "skipped"} else None
            next_stages.append(
                stage.model_copy(
                    update={
                        "status": status,
                        "started_at": started_at,
                        "finished_at": finished_at,
                        "summary": summary or stage.summary,
                        "error": error or stage.error,
                    }
                )
            )
        stages[:] = next_stages
        self._run_store.save_stages(run_id, stages)
        run_status = "failed" if status == "failed" else "running"
        detail = self._run_store.get_run(run_id).model_copy(update={"current_stage": stage_key, "status": run_status})
        self._run_store.save_run(detail)

    def _build_open_gaps(self, core_data: dict[str, Any]) -> list[str]:
        gaps: list[str] = []
        for symbol in ["SPY", "QQQ", "IWM", "^VIX"]:
            frame = core_data.get(symbol)
            if frame is None or frame.empty:
                gaps.append(f"缺少 {symbol} 日线")
        gaps.extend(
            [
                "缺少 VIX 期限结构",
                "缺少交易所级 breadth 原始数据",
                "缺少未来三日宏观与财报事件原始日历",
                "缺少股票级 RS 龙头横截面",
            ]
        )
        return gaps

    def _build_slot_queries(self, input_bundle: MarketInputBundle) -> dict[str, str]:
        as_of = input_bundle.as_of_date.isoformat()
        return {
            "macro_calendar": f"US macro calendar next 3 trading days around {as_of}",
            "earnings_watch": f"Major US earnings next 3 trading days around {as_of} impacting SPY QQQ IWM",
            "policy_geopolitics": f"US policy regulation or geopolitical risks for equities around {as_of}",
            "risk_sentiment": f"US equity risk sentiment volatility liquidity context around {as_of}",
            "market_structure_optional": "US market breadth leadership context when exchange breadth data is unavailable",
        }

    def _judgment_schema(self, keys: list[str]) -> dict[str, Any]:
        card = {
            "type": "object",
            "additionalProperties": False,
            "required": ["label", "summary", "confidence", "facts_used", "uncertainties", "action"],
            "properties": {
                "label": {"type": "string"},
                "summary": {"type": "string"},
                "confidence": {"type": "number"},
                "facts_used": {"type": "array", "items": {"type": "string"}},
                "uncertainties": {"type": "array", "items": {"type": "string"}},
                "action": {"type": "string"},
            },
        }
        return {
            "type": "object",
            "additionalProperties": False,
            "required": keys,
            "properties": {key: card for key in keys},
        }

    def _reconcile_stages_with_run(
        self,
        run: MarketMonitorRunDetail,
        stages_response: MarketMonitorRunStagesResponse,
    ) -> MarketMonitorRunStagesResponse:
        adjusted_stages: list[MarketMonitorRunStageDetail] = []
        failed_stage_present = any(stage.status == "failed" for stage in stages_response.stages)

        for stage in stages_response.stages:
            updated_stage = stage
            if run.status == "running" and run.current_stage in STAGE_KEYS and stage.stage_key == run.current_stage:
                if stage.status != "running":
                    updated_stage = stage.model_copy(
                        update={
                            "status": "running",
                            "finished_at": None,
                        }
                    )
            elif run.status == "completed" and stage.stage_key == "execution_decision" and stage.status != "completed":
                updated_stage = stage.model_copy(
                    update={
                        "status": "completed",
                        "finished_at": stage.finished_at or run.finished_at,
                    }
                )
            elif (
                run.status == "failed"
                and not failed_stage_present
                and run.current_stage in STAGE_KEYS
                and stage.stage_key == run.current_stage
            ):
                updated_stage = stage.model_copy(
                    update={
                        "status": "failed",
                        "finished_at": stage.finished_at or run.finished_at,
                        "error": stage.error or {"message": run.error_message or "运行失败"},
                    }
                )
            adjusted_stages.append(updated_stage)

        return MarketMonitorRunStagesResponse(run_id=stages_response.run_id, stages=adjusted_stages)

