import unittest
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.errors import MarketMonitorError, MarketMonitorNotFoundError
from tradingagents.web.market_monitor.data import _expected_market_close_date, _is_cache_usable, _required_trading_days
from tradingagents.web.market_monitor.metrics import build_market_snapshot
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorRunCreateRequest,
    MarketMonitorRunStageDetail,
)
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
            "counts": {"cache_hit": 8, "refreshed": 3, "stale_fallback": 1, "empty": 0},
            "symbols": [
                {"symbol": "SPY", "cache_state": "cache_hit", "rows": 320, "expected_close_date": "2026-04-10"},
                {"symbol": "QQQ", "cache_state": "refreshed", "rows": 320, "expected_close_date": "2026-04-10"},
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
        friday_frame = _make_frame(100, days=_required_trading_days(60))

        self.assertFalse(_is_cache_usable(friday_frame.iloc[:-1], date(2026, 4, 13), 60))
        self.assertTrue(_is_cache_usable(friday_frame, date(2026, 4, 12), 60))
        self.assertEqual(_expected_market_close_date(date(2026, 4, 12)), pd.Timestamp("2026-04-10"))
        self.assertEqual(_expected_market_close_date(date(2026, 4, 3)), pd.Timestamp("2026-04-02"))

    def test_metrics_builder_returns_local_data_and_derived_metrics(self) -> None:
        dataset = _complete_dataset()
        universe = get_market_monitor_universe()

        local_market_data, derived_metrics = build_market_snapshot(
            dataset["core"], universe["market_proxies"]
        )

        self.assertIn("SPY", local_market_data)
        self.assertIn("breadth_above_200dma_pct", derived_metrics)
        self.assertIn("spy_range_position_3m_pct", derived_metrics)

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
            self.assertTrue((run_dir / "stages.json").exists())
            self.assertTrue((run_dir / "evidence.json").exists())
            self.assertTrue((run_dir / "events.log").exists())
            input_stage = next(stage for stage in stages.stages if stage.stage_key == "input_bundle")
            self.assertIn("cache_counts", input_stage.summary)
            self.assertIn("cache_symbols", input_stage.summary)
            logs = service.list_run_logs(response.run_id)
            self.assertTrue(any("cache_hit=8" in entry.content for entry in logs))

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

    def test_get_run_stages_masks_completed_current_stage_while_run_is_still_running(self) -> None:
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
            self.assertEqual(execution_stage.status, "running")
            self.assertIsNone(execution_stage.finished_at)

    def test_get_run_stages_marks_current_stage_failed_when_run_failed_but_stages_lag(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=CapturingExecutor())
            run = service._run_store.create_run(date(2026, 4, 10))
            failed_detail = service._run_store.get_run(run.run_id).model_copy(
                update={
                    "status": "failed",
                    "current_stage": "judgment_group_b",
                    "finished_at": datetime(2026, 4, 10, 9, 30, 0),
                    "error_message": "judgment_group_b failed",
                }
            )
            service._run_store.save_run(failed_detail)
            service._run_store.save_stages(
                run.run_id,
                [
                    MarketMonitorRunStageDetail(stage_key="input_bundle", label="本地输入摘要", status="completed"),
                    MarketMonitorRunStageDetail(stage_key="search_slots", label="搜索补数", status="completed"),
                    MarketMonitorRunStageDetail(stage_key="fact_sheet", label="事实整编", status="completed"),
                    MarketMonitorRunStageDetail(stage_key="judgment_group_a", label="环境与系统风险裁决", status="completed"),
                    MarketMonitorRunStageDetail(stage_key="judgment_group_b", label="短线与事件裁决", status="running"),
                    MarketMonitorRunStageDetail(stage_key="execution_decision", label="执行建议", status="pending"),
                ],
            )

            stages = service.get_run_stages(run.run_id)

            failed_stage = next(stage for stage in stages.stages if stage.stage_key == "judgment_group_b")
            self.assertEqual(failed_stage.status, "failed")
            self.assertTrue(failed_stage.error)

    def test_service_recover_tolerates_missing_stage_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=CapturingExecutor())
            run = first_service._run_store.create_run(date(2026, 4, 10))
            run_dir = first_service._run_store.resolve_run_dir(run.run_id)
            (run_dir / "stages.json").unlink()

            restarted_service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=CapturingExecutor())

            recovered = restarted_service.get_run(run.run_id)
            self.assertEqual(recovered.status, "failed")
            self.assertIn("损坏", recovered.error_message or "")

    def test_service_recover_marks_abandoned_run_as_failed_after_restart(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=CapturingExecutor())

            response = first_service.create_run(MarketMonitorRunCreateRequest(as_of_date=date(2026, 4, 10)))
            stale_before = first_service.get_run(response.run_id)
            self.assertEqual(stale_before.status, "running")
            self.assertEqual(stale_before.current_stage, "pending")

            restarted_service = MarketMonitorService(run_root=root / "runs", prompt_root=root / "prompts", run_executor=CapturingExecutor())

            recovered = restarted_service.get_run(response.run_id)
            self.assertEqual(recovered.status, "failed")
            self.assertEqual(recovered.current_stage, "failed")
            self.assertIsNotNone(recovered.finished_at)
            self.assertIn("中断", recovered.error_message or "")


if __name__ == "__main__":
    unittest.main()
