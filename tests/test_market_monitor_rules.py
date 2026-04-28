import unittest
from datetime import date
from typing import Any
from unittest.mock import patch

import pandas as pd

from tests.market_monitor_v231_fixtures import (
    fixture_fact_sheet,
    fixture_panic_card,
    fixture_score_card,
    fixture_snapshot,
    fixture_style_effectiveness,
    fixture_system_risk_card,
)
from tradingagents.web.market_monitor.data import _expected_market_close_date
from tradingagents.web.market_monitor.factors import build_execution_card, build_input_bundle, build_panic_card
from tradingagents.web.market_monitor.metrics import build_market_snapshot
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorHistoryRequest,
    MarketMonitorSnapshotRequest,
)
from tradingagents.web.market_monitor.snapshot_service import MarketMonitorSnapshotService
from tradingagents.web.market_monitor.universe import get_market_monitor_universe


class _FakeResponse:
    content = "not json"


class _FakeLlm:
    def invoke(self, messages):
        return _FakeResponse()


class _FakeClient:
    def get_llm(self):
        return _FakeLlm()


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
    symbols: list[str] = []
    for values in universe.values():
        for symbol in values:
            if symbol not in symbols:
                symbols.append(symbol)
    core = {symbol: _make_frame(100 + idx * 3) for idx, symbol in enumerate(symbols)}
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


class MarketMonitorRulesTests(unittest.TestCase):
    def test_symbol_cache_requires_requested_trading_day(self) -> None:
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

    def test_snapshot_service_builds_v231_snapshot(self) -> None:
        dataset = _complete_dataset()
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=_FakeClient(),
        ):
            service = MarketMonitorSnapshotService()

        with patch(
            "tradingagents.web.market_monitor.snapshot_service.build_market_dataset",
            return_value=dataset,
        ):
            snapshot = service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertEqual(snapshot.scorecard_version, "2.3.1")
        self.assertEqual(snapshot.as_of_date, date(2026, 4, 10))
        self.assertEqual(snapshot.data_mode, "daily")
        self.assertTrue(snapshot.execution_card.regime_label)
        self.assertEqual(snapshot.execution_card.signal_confirmation.current_regime_observations, 1)
        self.assertEqual(snapshot.execution_card.signal_confirmation.risk_loosening_unlock_in_observations, 2)
        self.assertTrue(snapshot.input_data_status.core_symbols_available)
        self.assertTrue(snapshot.missing_data)
        self.assertEqual(snapshot.event_fact_sheet, [])
        self.assertTrue(snapshot.long_term_score.factor_breakdown)
        self.assertIsNotNone(snapshot.long_term_score.deterministic_score)
        self.assertGreaterEqual(snapshot.long_term_score.confidence, 0)
        self.assertLessEqual(snapshot.long_term_score.confidence, 1)
        self.assertIn("风险", snapshot.system_risk_score.slope_state)
        self.assertGreaterEqual(snapshot.panic_reversal_score.score, 0)
        self.assertLessEqual(snapshot.panic_reversal_score.score, 100)
        self.assertEqual(len(snapshot.prompt_traces), 6)
        self.assertEqual(
            [trace.card_type for trace in snapshot.prompt_traces],
            ["long_term", "short_term", "system_risk", "style", "panic", "execution"],
        )

    def test_snapshot_service_data_status_uses_open_gaps(self) -> None:
        dataset = _complete_dataset()
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=_FakeClient(),
        ):
            service = MarketMonitorSnapshotService()

        with patch(
            "tradingagents.web.market_monitor.snapshot_service.build_market_dataset",
            return_value=dataset,
        ):
            data_status = service.get_data_status(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertEqual(data_status.as_of_date, date(2026, 4, 10))
        self.assertEqual(data_status.data_mode, "daily")
        self.assertIn("未注入宏观日历、财报日历、政策/地缘与突发新闻搜索事实", data_status.open_gaps)
        self.assertTrue(data_status.missing_data)
        self.assertEqual(data_status.event_fact_sheet, [])

    def test_snapshot_service_uses_intraday_dataset_status(self) -> None:
        dataset = _complete_dataset()
        dataset["data_mode"] = "intraday_delayed"
        dataset["cache_summary"]["data_mode"] = "intraday_delayed"
        dataset["cache_summary"]["interval"] = "5m"
        dataset["cache_summary"]["includes_prepost"] = False
        dataset["cache_summary"]["symbols"][0]["partial"] = True
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=_FakeClient(),
        ):
            service = MarketMonitorSnapshotService()

        with patch(
            "tradingagents.web.market_monitor.snapshot_service.build_market_dataset",
            return_value=dataset,
        ) as dataset_mock:
            snapshot = service.get_snapshot(
                MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10), data_mode="intraday_delayed")
            )

        self.assertEqual(dataset_mock.call_args.kwargs["data_mode"], "intraday_delayed")
        self.assertEqual(snapshot.data_mode, "intraday_delayed")
        self.assertEqual(snapshot.data_freshness, "intraday_fresh")
        self.assertEqual(snapshot.input_data_status.interval, "5m")
        self.assertFalse(snapshot.input_data_status.includes_prepost)
        self.assertEqual(snapshot.input_data_status.partial_symbols, ["SPY"])

    def test_intraday_missing_core_symbol_is_not_fresh(self) -> None:
        dataset = _complete_dataset()
        dataset["core"]["QQQ"] = pd.DataFrame()
        dataset["data_mode"] = "intraday_delayed"
        dataset["cache_summary"]["symbols"].append(
            {
                "symbol": "QQQ",
                "cache_state": "cache_disabled",
                "result_state": "empty",
                "rows": 0,
                "expected_close_date": "2026-04-10",
                "cache_end_date": None,
                "last_successful_refresh_at": None,
                "reason": "yfinance 未返回可用 5m 数据",
                "partial": False,
            }
        )

        bundle = build_input_bundle(as_of_date=date(2026, 4, 10), dataset=dataset, universe=get_market_monitor_universe())

        self.assertEqual(bundle.data_freshness, "intraday_stale")
        self.assertIn("QQQ", bundle.input_data_status.core_symbols_missing)

    def test_snapshot_service_history_disables_event_news_fetches(self) -> None:
        dataset = _complete_dataset()
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=_FakeClient(),
        ), patch(
            "tradingagents.web.market_monitor.snapshot_service.build_market_dataset",
            return_value=dataset,
        ) as dataset_mock:
            service = MarketMonitorSnapshotService()
            service.get_history_snapshots(
                MarketMonitorHistoryRequest(as_of_date=date(2026, 4, 10), days=2),
                trade_dates=[date(2026, 4, 9), date(2026, 4, 10)],
            )

        self.assertEqual(dataset_mock.call_count, 2)
        self.assertTrue(all(call.kwargs["include_event_news"] is False for call in dataset_mock.call_args_list))

    def test_snapshot_service_history_returns_requested_days(self) -> None:
        service = MarketMonitorSnapshotService()
        snapshots = [
            fixture_snapshot(as_of_date=date(2026, 4, 8)),
            fixture_snapshot(as_of_date=date(2026, 4, 9)),
            fixture_snapshot(as_of_date=date(2026, 4, 10)),
        ]

        history = service.build_history_response(date(2026, 4, 10), snapshots)

        self.assertEqual(history.as_of_date, date(2026, 4, 10))
        self.assertEqual(len(history.points), 3)
        self.assertEqual(sorted(point.trade_date for point in history.points), [point.trade_date for point in history.points])
        self.assertTrue(all(point.scorecard_version == "2.3.1" for point in history.points))
        self.assertTrue(all(point.panic_state for point in history.points))

    def test_snapshot_service_history_skips_holidays(self) -> None:
        service = MarketMonitorSnapshotService()
        trade_dates = service.resolve_history_trade_dates(
            MarketMonitorHistoryRequest(as_of_date=date(2026, 4, 3), days=2)
        )

        self.assertEqual(trade_dates, [date(2026, 4, 1), date(2026, 4, 2)])

    def test_snapshot_service_event_fact_sheet_is_empty_without_structured_events(self) -> None:
        dataset = _complete_dataset()
        universe = get_market_monitor_universe()
        bundle = build_input_bundle(as_of_date=date(2026, 4, 10), dataset=dataset, universe=universe)

        from tradingagents.web.market_monitor.factors import build_event_fact_sheet

        self.assertEqual(build_event_fact_sheet(bundle), [])

    def test_snapshot_service_does_not_mark_events_missing_when_fact_sheet_has_events(self) -> None:
        dataset = _complete_dataset()
        fact_sheet = fixture_fact_sheet(as_of_date=date(2026, 4, 10), include_event=True)
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=_FakeClient(),
        ):
            service = MarketMonitorSnapshotService()

        snapshot = service._build_snapshot(date(2026, 4, 10), dataset, fact_sheet_override=fact_sheet)

        self.assertTrue(snapshot.event_fact_sheet)
        self.assertNotIn("event_fact_sheet", [item.field for item in snapshot.missing_data])
        self.assertNotIn("未注入宏观日历、财报日历、政策/地缘与突发新闻搜索事实", snapshot.fact_sheet.open_gaps)

    def test_risk_loosening_requires_three_consecutive_observations(self) -> None:
        previous = fixture_snapshot().model_copy(
            update={
                "execution_card": fixture_snapshot().execution_card.model_copy(
                    update={
                        "regime_label": "红灯",
                        "conflict_mode": "上一轮防守状态",
                        "total_exposure_range": "0%-20%",
                        "new_position_allowed": False,
                        "chase_breakout_allowed": False,
                        "dip_buy_allowed": False,
                        "overnight_allowed": False,
                        "single_position_cap": "5%",
                        "daily_risk_budget": "0.25R",
                    }
                )
            }
        )

        first = build_execution_card(
            fixture_score_card(deterministic_score=90, score=90, zone="强趋势区"),
            fixture_score_card(deterministic_score=90, score=90, zone="高胜率区", recommended_exposure=None),
            fixture_system_risk_card(score=10),
            fixture_style_effectiveness(),
            [],
            previous_snapshots=[previous],
        )
        self.assertEqual(first.regime_label, "红灯")
        self.assertFalse(first.new_position_allowed)
        self.assertEqual(first.signal_confirmation.current_regime_observations, 1)
        self.assertEqual(first.signal_confirmation.risk_loosening_unlock_in_observations, 2)

        second_snapshot = previous.model_copy(update={"execution_card": first})
        second = build_execution_card(
            fixture_score_card(deterministic_score=90, score=90, zone="强趋势区"),
            fixture_score_card(deterministic_score=90, score=90, zone="高胜率区", recommended_exposure=None),
            fixture_system_risk_card(score=10),
            fixture_style_effectiveness(),
            [],
            previous_snapshots=[previous, second_snapshot],
        )
        self.assertFalse(second.new_position_allowed)
        self.assertEqual(second.signal_confirmation.current_regime_observations, 2)
        self.assertEqual(second.signal_confirmation.risk_loosening_unlock_in_observations, 1)

        third_snapshot = previous.model_copy(update={"execution_card": second})
        third = build_execution_card(
            fixture_score_card(deterministic_score=90, score=90, zone="强趋势区"),
            fixture_score_card(deterministic_score=90, score=90, zone="高胜率区", recommended_exposure=None),
            fixture_system_risk_card(score=10),
            fixture_style_effectiveness(),
            [],
            previous_snapshots=[previous, second_snapshot, third_snapshot],
        )
        self.assertEqual(third.regime_label, "绿灯")
        self.assertTrue(third.new_position_allowed)
        self.assertEqual(third.signal_confirmation.risk_loosening_unlock_in_observations, 0)

    def test_risk_tightening_applies_immediately_and_panic_refreshes_count(self) -> None:
        previous = fixture_snapshot().model_copy(
            update={
                "execution_card": fixture_snapshot().execution_card.model_copy(update={"regime_label": "绿灯", "total_exposure_range": "80%-100%"}),
                "panic_reversal_score": fixture_panic_card(state="panic_watch"),
            }
        )
        current = build_execution_card(
            fixture_score_card(deterministic_score=20, score=20, zone="防守区"),
            fixture_score_card(deterministic_score=20, score=20, zone="弱势区", recommended_exposure=None),
            fixture_system_risk_card(score=75),
            fixture_style_effectiveness(),
            [],
            previous_snapshots=[previous],
        )
        self.assertEqual(current.regime_label, "红灯-高压")
        self.assertFalse(current.new_position_allowed)
        self.assertEqual(current.signal_confirmation.risk_loosening_unlock_in_observations, 0)

        dataset = _complete_dataset()
        bundle = build_input_bundle(as_of_date=date(2026, 4, 10), dataset=dataset, universe=get_market_monitor_universe())
        panic = build_panic_card(bundle, 30, previous_snapshots=[previous])
        if panic.state == "panic_watch":
            self.assertEqual(panic.refreshes_held, 2)
        elif panic.state == "无信号":
            self.assertEqual(panic.refreshes_held, 0)

    def test_snapshot_service_open_gaps_include_missing_core_series(self) -> None:
        service = MarketMonitorSnapshotService()
        universe = get_market_monitor_universe()
        dataset = _complete_dataset()
        dataset["core"]["QQQ"] = pd.DataFrame()
        bundle = build_input_bundle(as_of_date=date(2026, 4, 10), dataset=dataset, universe=universe)
        gaps = service._build_open_gaps(bundle, [])

        self.assertIn("缺少 QQQ 1d 行情", gaps)
        self.assertIn("未注入宏观日历、财报日历、政策/地缘与突发新闻搜索事实", gaps)


if __name__ == "__main__":
    unittest.main()
