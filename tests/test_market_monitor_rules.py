import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.data import _expected_market_close_date, _is_cache_usable
from tradingagents.web.market_monitor.metrics import build_market_snapshot
from tradingagents.web.market_monitor.schemas import MarketMonitorRunCreateRequest
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


def _complete_dataset() -> dict[str, dict[str, pd.DataFrame]]:
    universe = get_market_monitor_universe()
    core = {symbol: _make_frame(100 + idx * 3) for idx, symbol in enumerate(universe["core_index_etfs"])}
    core.update({symbol: _make_frame(80 + idx * 2) for idx, symbol in enumerate(universe["sector_etfs"])})
    core["^VIX"] = _make_frame(18, days=320)
    return {"core": core}


class MarketMonitorRulesTests(unittest.TestCase):
    def test_symbol_cache_requires_requested_trading_day(self) -> None:
        friday_frame = _make_frame(100, days=120)

        self.assertFalse(_is_cache_usable(friday_frame, date(2026, 4, 13), 60))
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
                return_value=None,
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
            self.assertGreaterEqual(len(prompts), 4)
            self.assertTrue(
                all(
                    Path(prompt.file_path).as_posix().startswith(
                        (root / "runs" / "2026-04-10" / response.run_id).as_posix()
                    )
                    for prompt in prompts
                )
            )
            self.assertTrue(
                (root / "runs" / "2026-04-10" / response.run_id / "prompts" / "judgment_group_a" / "attempt-1.json")
                .exists()
            )

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
