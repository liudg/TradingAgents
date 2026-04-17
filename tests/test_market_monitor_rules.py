import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.errors import (
    MarketMonitorConflictError,
    MarketMonitorError,
    MarketMonitorNotFoundError,
)
from tradingagents.web.market_monitor.data import _expected_market_close_date, _required_trading_days
from tradingagents.web.market_monitor.metrics import build_market_snapshot
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorRunCleanupRequest,
    MarketMonitorRunCreateRequest,
    MarketMonitorRunStageDetail,
)
from tradingagents.web.market_monitor.run_store import MonitorRunStore
from tradingagents.web.market_monitor.service import MarketMonitorService
from tradingagents.web.market_monitor.universe import get_market_monitor_universe


class CapturingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = []

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self.calls.append((fn, args, kwargs))
        return None


def _make_frame(base: float, days: int = 320) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp("2026-04-10"), periods=days, freq="B")
    close = pd.Series([base + i * 0.4 for i in range(days)], index=index)
    return pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": pd.Series([1_000_000 + i * 100 for i in range(days)], index=index),
        }
    )


def _complete_dataset() -> dict[str, Any]:
    universe = get_market_monitor_universe()
    core = {symbol: _make_frame(100 + idx * 3) for idx, symbol in enumerate(universe["core_index_etfs"])}
    core.update({symbol: _make_frame(80 + idx * 2) for idx, symbol in enumerate(universe["sector_etfs"])})
    core["^VIX"] = _make_frame(18, days=320)
    return {
        "core": core,
        "cache_summary": {
            "counts": {
                "cache_missing": 1,
                "cache_corrupted": 1,
                "cache_invalid_structure": 1,
                "cache_stale": 1,
                "cache_hit": 8,
            },
            "result_counts": {
                "cache_hit": 8,
                "refreshed": 3,
                "stale_fallback": 1,
                "empty": 0,
            },
            "symbols": [
                {
                    "symbol": "SPY",
                    "cache_state": "cache_hit",
                    "result_state": "cache_hit",
                    "rows": 320,
                    "expected_close_date": "2026-04-10",
                    "cache_end_date": "2026-04-10",
                    "last_successful_refresh_at": "2026-04-10T00:00:00+00:00",
                    "reason": None,
                },
                {
                    "symbol": "QQQ",
                    "cache_state": "cache_missing",
                    "result_state": "refreshed",
                    "rows": 320,
                    "expected_close_date": "2026-04-10",
                    "cache_end_date": "2026-04-10",
                    "last_successful_refresh_at": "2026-04-10T00:00:00+00:00",
                    "reason": None,
                },
            ],
        },
    }


def _llm_payloads() -> list[dict[str, Any]]:
    return [
        {
            "slots": {
                "macro_calendar": [
                    {
                        "title": "FOMC schedule",
                        "summary": "未来三日存在美联储事件窗口。",
                        "source": "fed.gov",
                        "published_at": "2026-04-10T08:00:00",
                    }
                ],
                "earnings_watch": [],
                "policy_geopolitics": [],
                "risk_sentiment": [],
                "market_structure_optional": [],
            }
        },
        {
            "long_term_card": {
                "label": "偏多",
                "summary": "长线环境偏多。",
                "confidence": 0.78,
                "facts_used": ["SPY 收盘走强"],
                "uncertainties": ["缺少 breadth 原始交易所数据"],
                "action": "保留趋势仓位。",
            },
            "system_risk_card": {
                "label": "可控",
                "summary": "系统性风险暂时可控。",
                "confidence": 0.74,
                "facts_used": ["VIX 仍在可控区间"],
                "uncertainties": ["缺少 VIX 期限结构"],
                "action": "维持标准风险预算。",
            },
        },
        {
            "short_term_card": {
                "label": "可做",
                "summary": "短线仍可参与。",
                "confidence": 0.7,
                "facts_used": ["SPY 5 日动能为正"],
                "uncertainties": ["缺少未来三日财报原始日历"],
                "action": "低吸优先。",
            },
            "event_risk_card": {
                "label": "事件密集",
                "summary": "未来三日事件偏密集。",
                "confidence": 0.69,
                "facts_used": ["存在宏观事件窗口"],
                "uncertainties": ["缺少完整事件原始日历"],
                "action": "事件前避免追高。",
            },
            "panic_card": {
                "label": "未激活",
                "summary": "尚未触发恐慌反转。",
                "confidence": 0.73,
                "facts_used": ["VIX 未显著飙升"],
                "uncertainties": ["缺少情绪横截面"],
                "action": "无需切换恐慌策略。",
            },
        },
        {
            "summary": "维持偏多参与，但控制事件窗口内的追高和单笔风险。",
            "confidence": 0.72,
            "decision_basis": ["长线偏多", "系统风险可控", "事件窗口存在扰动"],
            "tradeoffs": ["保持参与度，同时降低事件前进攻性"],
            "risk_flags": ["未来三日事件密集"],
            "actions": ["总仓位 50%-70%", "优先低吸，减少追高"],
        },
    ]


class MarketMonitorRulesTests(unittest.TestCase):
    def test_symbol_cache_requires_requested_trading_day(self) -> None:
        self.assertEqual(_expected_market_close_date(date(2026, 4, 12)), pd.Timestamp("2026-04-10"))
        self.assertEqual(_expected_market_close_date(date(2026, 4, 3)), pd.Timestamp("2026-04-02"))

    def test_run_store_resolves_run_directory_without_index(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = MonitorRunStore(Path(temp_dir) / "runs")
            run = store.create_run(date(2026, 4, 10))

            resolved = store.resolve_run_dir(run.run_id)

            self.assertEqual(resolved, store.root / "2026-04-10" / run.run_id)
            self.assertFalse((store.root / "run_index.json").exists())

    def test_metrics_builder_returns_local_data_and_derived_metrics(self) -> None:
        dataset = _complete_dataset()
        universe = get_market_monitor_universe()

        local_market_data, derived_metrics = build_market_snapshot(
            dataset["core"], universe["market_proxies"]
        )

        self.assertIn("SPY", local_market_data)
        self.assertIn("breadth_above_200dma_pct", derived_metrics)
        self.assertIn("spy_range_position_3m_pct", derived_metrics)

    def test_run_store_list_logs_tolerates_invalid_jsonl_line(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = MonitorRunStore(Path(temp_dir) / "runs")
            run = store.create_run(date(2026, 4, 10))
            events_path = store.resolve_run_dir(run.run_id) / "artifacts" / "events.jsonl"
            events_path.parent.mkdir(parents=True, exist_ok=True)
            events_path.write_text(
                '{"timestamp":"2026-04-10T08:00:00+00:00","level":"Stage","message":"ok"}\nnot-json\n',
                encoding="utf-8",
            )

            logs = store.list_logs(run.run_id)

            self.assertEqual(logs[0].level, "Stage")
            self.assertEqual(logs[0].content, "ok")
            self.assertIsNone(logs[0].event_type)
            self.assertIsNone(logs[0].stage_key)
            self.assertEqual(logs[0].details, {})
            self.assertEqual(logs[1].level, "Raw")
            self.assertEqual(logs[1].content, "not-json")
            self.assertIsNone(logs[1].event_type)
            self.assertIsNone(logs[1].stage_key)
            self.assertEqual(logs[1].details, {})

    def test_create_run_persists_completed_stages(self) -> None:
        dataset = _complete_dataset()
        with TemporaryDirectory() as temp_dir:
            executor = CapturingExecutor()
            root = Path(temp_dir)
            service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=executor)

            with patch(
                "tradingagents.web.market_monitor.service.build_market_dataset",
                return_value=dataset,
            ), patch.object(
                service._llm,
                "request_json",
                side_effect=_llm_payloads(),
            ):
                response = service.create_run(MarketMonitorRunCreateRequest(as_of_date=date(2026, 4, 10)))
                self.assertEqual(response.status, "running")
                self.assertEqual(len(executor.calls), 1)
                fn, args, kwargs = executor.calls[0]
                fn(*args, **kwargs)

            detail = service.get_run(response.run_id)
            stages = service.get_run_stages(response.run_id)
            self.assertEqual(detail.status, "completed")
            self.assertEqual(stages.stages[-1].stage_key, "execution_decision")
            self.assertEqual(stages.stages[-1].status, "completed")
            self.assertIsNotNone(detail.result)
            run_dir = root / "runs" / "2026-04-10" / response.run_id
            self.assertTrue((run_dir / "run.json").exists())
            self.assertTrue((run_dir / "artifacts" / "stages.json").exists())
            self.assertTrue((run_dir / "artifacts" / "evidence.json").exists())
            self.assertTrue((run_dir / "artifacts" / "events.jsonl").exists())
            input_stage = next(stage for stage in stages.stages if stage.stage_key == "input_bundle")
            self.assertIn("cache_counts", input_stage.summary)
            self.assertIn("cache_symbols", input_stage.summary)
            logs = service.list_run_logs(response.run_id)
            self.assertTrue(any("cache_corrupted=1" in entry.content for entry in logs))
            self.assertTrue(any("cache_hit=8" in entry.content for entry in logs))
            self.assertTrue(any(entry.level == "Response" and entry.content == "市场监控运行完成" for entry in logs))
            self.assertTrue(
                any(
                    entry.level == "Stage"
                    and entry.event_type == "stage_completed"
                    and entry.stage_key == "input_bundle"
                    and entry.details.get("cache_counts")
                    for entry in logs
                )
            )
            self.assertTrue(
                any(
                    entry.level == "Stage"
                    and entry.event_type == "stage_completed"
                    and entry.stage_key == "execution_decision"
                    and entry.details.get("confidence") == 0.72
                    for entry in logs
                )
            )

    def test_create_run_fails_when_llm_stage_fails(self) -> None:
        dataset = _complete_dataset()
        with TemporaryDirectory() as temp_dir:
            executor = CapturingExecutor()
            root = Path(temp_dir)
            service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=executor)

            with patch(
                "tradingagents.web.market_monitor.service.build_market_dataset",
                return_value=dataset,
            ), patch.object(
                service._llm,
                "request_json",
                side_effect=[
                    _llm_payloads()[0],
                    MarketMonitorError("judgment_group_a 阶段模型请求失败: timed out"),
                ],
            ):
                response = service.create_run(MarketMonitorRunCreateRequest(as_of_date=date(2026, 4, 10)))
                fn, args, kwargs = executor.calls[0]
                fn(*args, **kwargs)

            detail = service.get_run(response.run_id)
            stages = service.get_run_stages(response.run_id)
            self.assertEqual(detail.status, "failed")
            self.assertIn("judgment_group_a", detail.error_message or "")
            failed_stage = next(stage for stage in stages.stages if stage.stage_key == "judgment_group_a")
            self.assertEqual(failed_stage.status, "failed")

    def test_create_run_keeps_prompts_under_same_run_directory(self) -> None:
        dataset = _complete_dataset()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executor = CapturingExecutor()
            service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=executor)

            with patch(
                "tradingagents.web.market_monitor.service.build_market_dataset",
                return_value=dataset,
            ), patch.dict("os.environ", {"CODEX_API_KEY": ""}, clear=False):
                response = service.create_run(MarketMonitorRunCreateRequest(as_of_date=date(2026, 4, 10)))
                fn, args, kwargs = executor.calls[0]
                fn(*args, **kwargs)

            prompts = service.list_run_prompts(response.run_id)
            self.assertEqual(len(prompts), 1)
            self.assertTrue(
                all(
                    Path(prompt.file_path).as_posix().startswith(
                        (root / "runs" / "2026-04-10" / response.run_id).as_posix()
                    )
                    for prompt in prompts
                )
            )

    def test_create_run_fails_on_unknown_search_slot_key(self) -> None:
        dataset = _complete_dataset()
        with TemporaryDirectory() as temp_dir:
            executor = CapturingExecutor()
            root = Path(temp_dir)
            service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=executor)

            with patch(
                "tradingagents.web.market_monitor.service.build_market_dataset",
                return_value=dataset,
            ), patch.object(
                service._llm,
                "request_json",
                return_value={
                    "slots": {
                        "unexpected_slot": [
                            {
                                "title": "unexpected",
                                "summary": "unexpected",
                                "source": "example.com",
                                "published_at": "2026-04-10T08:00:00",
                            }
                        ]
                    }
                },
            ):
                response = service.create_run(MarketMonitorRunCreateRequest(as_of_date=date(2026, 4, 10)))
                fn, args, kwargs = executor.calls[0]
                fn(*args, **kwargs)

            detail = service.get_run(response.run_id)
            self.assertEqual(detail.status, "failed")
            self.assertIn("未知槽位", detail.error_message or "")

    def test_list_run_prompts_raises_not_found_for_unknown_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=CapturingExecutor())

            with self.assertRaises(MarketMonitorNotFoundError):
                service.list_run_prompts("missing-run")

    def test_get_run_stages_returns_persisted_stage_state_without_reconciliation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=CapturingExecutor())
            run = service._run_store.create_run(date(2026, 4, 10))
            running_detail = service._run_store.get_run(run.run_id).model_copy(
                update={
                    "status": "running",
                    "current_stage": "execution_decision",
                }
            )
            service._run_store.save_run(running_detail)
            service._run_store.save_stages(
                run.run_id,
                [
                    MarketMonitorRunStageDetail(stage_key="input_bundle", label="本地输入摘要", status="completed"),
                    MarketMonitorRunStageDetail(stage_key="search_slots", label="搜索补数", status="completed"),
                    MarketMonitorRunStageDetail(stage_key="fact_sheet", label="事实整编", status="completed"),
                    MarketMonitorRunStageDetail(stage_key="judgment_group_a", label="环境与系统风险裁决", status="completed"),
                    MarketMonitorRunStageDetail(stage_key="judgment_group_b", label="短线与事件裁决", status="completed"),
                    MarketMonitorRunStageDetail(stage_key="execution_decision", label="执行建议", status="completed"),
                ],
            )

            stages = service.get_run_stages(run.run_id)

            execution_stage = next(stage for stage in stages.stages if stage.stage_key == "execution_decision")
            self.assertEqual(execution_stage.status, "completed")

    def test_service_restart_does_not_recover_or_mutate_running_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=CapturingExecutor())

            response = first_service.create_run(MarketMonitorRunCreateRequest(as_of_date=date(2026, 4, 10)))
            stale_before = first_service.get_run(response.run_id)
            self.assertEqual(stale_before.status, "running")
            self.assertEqual(stale_before.current_stage, "pending")

            restarted_service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=CapturingExecutor())

            recovered = restarted_service.get_run(response.run_id)
            self.assertEqual(recovered.status, "running")
            self.assertEqual(recovered.current_stage, "pending")
            self.assertIsNone(recovered.finished_at)

    def test_service_restart_allows_new_run_to_execute_while_stale_run_remains_running(self) -> None:
        dataset = _complete_dataset()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_service = MarketMonitorService(
                run_root=root / "runs",
                prompt_root=root / "prompts",
                run_executor=CapturingExecutor(),
            )
            stale_response = first_service.create_run(
                MarketMonitorRunCreateRequest(as_of_date=date(2026, 4, 10))
            )

            restarted_executor = CapturingExecutor()
            restarted_service = MarketMonitorService(
                run_root=root / "runs",
                prompt_root=root / "prompts",
                run_executor=restarted_executor,
            )

            with patch(
                "tradingagents.web.market_monitor.service.build_market_dataset",
                return_value=dataset,
            ), patch.object(
                restarted_service._llm,
                "request_json",
                side_effect=_llm_payloads(),
            ):
                new_response = restarted_service.create_run(
                    MarketMonitorRunCreateRequest(as_of_date=date(2026, 4, 10))
                )
                self.assertNotEqual(new_response.run_id, stale_response.run_id)
                self.assertEqual(new_response.status, "running")
                self.assertEqual(len(restarted_executor.calls), 1)
                fn, args, kwargs = restarted_executor.calls[0]
                fn(*args, **kwargs)

            self.assertEqual(restarted_service.get_run(stale_response.run_id).status, "running")
            self.assertEqual(restarted_service.get_run(new_response.run_id).status, "completed")

    def test_delete_run_rejects_running_and_cleanup_skips_running(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=CapturingExecutor())
            running_run = service._run_store.create_run(date(2026, 4, 10))
            failed_run = service._run_store.create_run(date(2026, 4, 9))
            failed_detail = service._run_store.get_run(failed_run.run_id).model_copy(
                update={
                    "status": "failed",
                    "current_stage": "failed",
                    "finished_at": datetime(2026, 4, 10, 9, 30, 0),
                    "error_message": "boom",
                }
            )
            service._run_store.save_run(failed_detail)

            with self.assertRaises(MarketMonitorConflictError):
                service.delete_run(running_run.run_id)

            cleanup = service.cleanup_runs(MarketMonitorRunCleanupRequest(delete_all_failed=True))

            self.assertEqual(cleanup.deleted_run_ids, [failed_run.run_id])
            self.assertEqual(cleanup.deleted_count, 1)
            self.assertEqual(service.get_run(running_run.run_id).status, "running")
            with self.assertRaises(MarketMonitorNotFoundError):
                service.get_run(failed_run.run_id)

    def test_service_cleanup_removes_expired_run_directories_on_startup(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            old_run_dir = root / "runs" / "2026-03-01" / "old-run"
            old_run_dir.mkdir(parents=True)
            (old_run_dir / "run.json").write_text("{}", encoding="utf-8")
            fresh_run_dir = root / "runs" / "2026-04-10" / "fresh-run"
            fresh_run_dir.mkdir(parents=True)
            (fresh_run_dir / "run.json").write_text("{}", encoding="utf-8")

            with patch("tradingagents.web.market_monitor.service.DEFAULT_CONFIG", {
                **__import__("tradingagents.default_config", fromlist=["DEFAULT_CONFIG"]).DEFAULT_CONFIG,
                "data_cache_dir": str(root / "cache"),
                "market_monitor_symbol_cache_retention_days": 30,
                "market_monitor_symbol_cache_cleanup_interval_seconds": 3600,
                "market_monitor_run_retention_days": 30,
            }), patch(
                "tradingagents.web.market_monitor.service.cleanup_symbol_daily_cache",
                return_value=1,
            ) as cleanup_symbol_cache, patch(
                "tradingagents.web.market_monitor.run_store.datetime"
            ) as mock_datetime:
                mock_datetime.now.return_value = datetime(2026, 4, 17, tzinfo=datetime.now().astimezone().tzinfo)
                mock_datetime.side_effect = datetime
                service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=CapturingExecutor())

            cleanup_symbol_cache.assert_called_once()
            self.assertFalse(old_run_dir.exists())
            self.assertTrue(fresh_run_dir.exists())
            service.shutdown()

    def test_service_create_run_triggers_runtime_cleanup_after_interval(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executor = CapturingExecutor()
            with patch("tradingagents.web.market_monitor.service.cleanup_symbol_daily_cache", return_value=0) as cleanup_symbol_cache:
                service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=executor)
                service._last_cache_cleanup_at = datetime(2026, 4, 10, tzinfo=timezone.utc)
                with patch("tradingagents.web.market_monitor.service.datetime") as mock_datetime:
                    mock_datetime.now.return_value = datetime(2026, 4, 10, 2, 0, tzinfo=timezone.utc)
                    mock_datetime.side_effect = datetime
                    with patch("tradingagents.web.market_monitor.service.DEFAULT_CONFIG", {
                        **__import__("tradingagents.default_config", fromlist=["DEFAULT_CONFIG"]).DEFAULT_CONFIG,
                        "market_monitor_symbol_cache_cleanup_interval_seconds": 3600,
                    }):
                        service.create_run(MarketMonitorRunCreateRequest(as_of_date=date(2026, 4, 10)))

            self.assertGreaterEqual(cleanup_symbol_cache.call_count, 2)


if __name__ == "__main__":
    unittest.main()
