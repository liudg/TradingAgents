import unittest
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.data import _expected_market_close_date
from tradingagents.web.market_monitor.metrics import build_market_snapshot
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorActionModifier,
    MarketMonitorEventRiskFlag,
    MarketMonitorExecutionCard,
    MarketMonitorFactSheet,
    MarketMonitorHistoryRequest,
    MarketMonitorIndexEventRisk,
    MarketMonitorPanicCard,
    MarketMonitorScoreCard,
    MarketMonitorSignalConfirmation,
    MarketMonitorSnapshotRequest,
    MarketMonitorSnapshotResponse,
    MarketMonitorSourceCoverage,
    MarketMonitorStockEventRisk,
    MarketMonitorStyleAssetLayer,
    MarketMonitorStyleEffectiveness,
    MarketMonitorStyleTacticLayer,
    MarketMonitorLayerMetric,
    MarketMonitorSystemRiskCard,
)
from tradingagents.web.market_monitor.snapshot_service import MarketMonitorSnapshotService
from tradingagents.web.market_monitor.universe import get_market_monitor_universe


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


def _build_minimal_snapshot(as_of_date: date) -> MarketMonitorSnapshotResponse:
    now = datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)
    event_risk = MarketMonitorEventRiskFlag(
        index_level=MarketMonitorIndexEventRisk(
            active=True,
            type="宏观窗口",
            days_to_event=1,
            action_modifier=MarketMonitorActionModifier(note="减少追高。"),
        ),
        stock_level=MarketMonitorStockEventRisk(earnings_stocks=["NVDA"], rule="财报股单票上限减半。"),
    )
    fact_sheet = MarketMonitorFactSheet(
        as_of_date=as_of_date,
        generated_at=now,
        local_facts={"spy_close": 523.1},
        derived_metrics={"breadth_above_200dma_pct": 63.0},
        open_gaps=["缺少交易所级 breadth 原始数据"],
        source_coverage=MarketMonitorSourceCoverage(
            completeness="medium",
            available_sources=["ETF/指数日线", "VIX 日线", "本地缓存"],
            missing_sources=["交易所级 breadth"],
            degraded=True,
        ),
    )
    return MarketMonitorSnapshotResponse(
        timestamp=now,
        as_of_date=as_of_date,
        data_freshness="delayed_15min",
        long_term_score=MarketMonitorScoreCard(
            score=68.5,
            zone="进攻区",
            delta_1d=2.1,
            delta_5d=8.2,
            slope_state="缓慢改善",
            summary="长线环境偏多。",
            action="建议维持趋势仓。",
        ),
        short_term_score=MarketMonitorScoreCard(
            score=61.3,
            zone="可做区",
            delta_1d=1.1,
            delta_5d=4.6,
            slope_state="缓慢改善",
            summary="短线环境允许参与。",
            action="优先低吸。",
        ),
        system_risk_score=MarketMonitorSystemRiskCard(
            score=34.6,
            zone="正常区",
            delta_1d=-1.2,
            delta_5d=-3.5,
            slope_state="缓慢恶化",
            summary="系统性风险可控。",
            action="维持常规风控。",
            liquidity_stress_score=31.2,
            risk_appetite_score=38.0,
        ),
        style_effectiveness=MarketMonitorStyleEffectiveness(
            tactic_layer=MarketMonitorStyleTacticLayer(
                trend_breakout=MarketMonitorLayerMetric(score=52, delta_5d=0.8, valid=False),
                dip_buy=MarketMonitorLayerMetric(score=66, delta_5d=3.4, valid=True),
                oversold_bounce=MarketMonitorLayerMetric(score=58, delta_5d=2.1, valid=True),
                top_tactic="回调低吸",
                avoid_tactic="趋势突破",
            ),
            asset_layer=MarketMonitorStyleAssetLayer(
                large_cap_tech=MarketMonitorLayerMetric(score=61, delta_5d=3.2, preferred=True),
                small_cap_momentum=MarketMonitorLayerMetric(score=44, delta_5d=-1.2, preferred=False),
                defensive=MarketMonitorLayerMetric(score=70, delta_5d=2.8, preferred=True),
                energy_cyclical=MarketMonitorLayerMetric(score=64, delta_5d=1.8, preferred=True),
                financials=MarketMonitorLayerMetric(score=49, delta_5d=0.4, preferred=False),
                preferred_assets=["防御板块", "能源/周期"],
                avoid_assets=["小盘高弹性"],
            ),
        ),
        execution_card=MarketMonitorExecutionCard(
            regime_label="黄绿灯-Swing",
            conflict_mode="长线中性+短线活跃+风险低",
            total_exposure_range="50%-70%",
            new_position_allowed=True,
            chase_breakout_allowed=True,
            dip_buy_allowed=True,
            overnight_allowed=True,
            leverage_allowed=False,
            single_position_cap="12%",
            daily_risk_budget="1.0R",
            tactic_preference="回调低吸 > 趋势突破",
            preferred_assets=["防御板块", "能源/周期"],
            avoid_assets=["小盘高弹性"],
            signal_confirmation=MarketMonitorSignalConfirmation(
                current_regime_observations=1,
                risk_loosening_unlock_in_observations=2,
                note="当前 regime 为新近状态，继续观察 2 个交易日。",
            ),
            event_risk_flag=event_risk,
            summary="当前处于黄绿灯-Swing，总仓建议 50%-70%。",
        ),
        panic_reversal_score=MarketMonitorPanicCard(
            score=41.2,
            zone="观察期",
            state="panic_watch",
            panic_extreme_score=38.0,
            selling_exhaustion_score=45.0,
            intraday_reversal_score=39.0,
            action="加入观察列表，等待确认。",
            stop_loss="ATR×1.0",
            profit_rule="达 1R 兑现 50%，余仓移止损到成本线。",
            timeout_warning=False,
            refreshes_held=0,
            early_entry_allowed=False,
            max_position_hint="20%-35%",
        ),
        event_risk_flag=event_risk,
        source_coverage=fact_sheet.source_coverage,
        degraded_factors=["广度因子使用 ETF 代理池近似"],
        notes=["已按代理池与降级规则输出结果。"],
        fact_sheet=fact_sheet,
        prompt_traces=[],
    )


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

    def test_snapshot_service_builds_formal_snapshot(self) -> None:
        dataset = _complete_dataset()
        service = MarketMonitorSnapshotService()

        with patch(
            "tradingagents.web.market_monitor.snapshot_service.build_market_dataset",
            return_value=dataset,
        ):
            snapshot = service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertEqual(snapshot.as_of_date, date(2026, 4, 10))
        self.assertTrue(snapshot.execution_card.regime_label)
        self.assertTrue(snapshot.execution_card.summary)
        self.assertEqual(snapshot.execution_card.signal_confirmation.current_regime_observations, 1)
        self.assertEqual(snapshot.execution_card.signal_confirmation.risk_loosening_unlock_in_observations, 2)
        self.assertIn("ETF/指数日线", snapshot.source_coverage.available_sources)
        self.assertIn("交易所级 breadth", snapshot.source_coverage.missing_sources)
        self.assertIn("广度因子使用 ETF 代理池近似", snapshot.degraded_factors)
        self.assertTrue(len(snapshot.notes) > 0)
        self.assertGreaterEqual(snapshot.long_term_score.score, 0)
        self.assertLessEqual(snapshot.long_term_score.score, 100)
        self.assertGreaterEqual(snapshot.short_term_score.score, 0)
        self.assertLessEqual(snapshot.short_term_score.score, 100)
        self.assertGreaterEqual(snapshot.system_risk_score.score, 0)
        self.assertLessEqual(snapshot.system_risk_score.score, 100)
        self.assertGreaterEqual(snapshot.panic_reversal_score.score, 0)
        self.assertLessEqual(snapshot.panic_reversal_score.score, 100)
        self.assertEqual(len(snapshot.prompt_traces), 7)
        self.assertEqual(
            [trace.card_type for trace in snapshot.prompt_traces],
            ["long_term", "short_term", "system_risk", "style", "event_risk", "panic", "execution"],
        )

    def test_snapshot_service_data_status_uses_open_gaps(self) -> None:
        dataset = _complete_dataset()
        service = MarketMonitorSnapshotService()

        with patch(
            "tradingagents.web.market_monitor.snapshot_service.build_market_dataset",
            return_value=dataset,
        ):
            data_status = service.get_data_status(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertEqual(data_status.as_of_date, date(2026, 4, 10))
        self.assertIn("缺少交易所级 breadth 原始数据", data_status.open_gaps)
        self.assertIn("广度因子使用 ETF 代理池近似", data_status.degraded_factors)
        self.assertTrue(data_status.source_coverage.degraded)

    def test_snapshot_service_history_returns_requested_days(self) -> None:
        service = MarketMonitorSnapshotService()
        snapshots = [
            _build_minimal_snapshot(date(2026, 4, 8)),
            _build_minimal_snapshot(date(2026, 4, 9)),
            _build_minimal_snapshot(date(2026, 4, 10)),
        ]

        history = service.build_history_response(date(2026, 4, 10), snapshots)

        self.assertEqual(history.as_of_date, date(2026, 4, 10))
        self.assertEqual(len(history.points), 3)
        self.assertEqual(sorted(point.trade_date for point in history.points), [point.trade_date for point in history.points])
        self.assertTrue(all(point.regime_label for point in history.points))

    def test_snapshot_service_history_skips_holidays(self) -> None:
        service = MarketMonitorSnapshotService()
        trade_dates = service.resolve_history_trade_dates(
            MarketMonitorHistoryRequest(as_of_date=date(2026, 4, 3), days=2)
        )

        self.assertEqual(trade_dates, [date(2026, 4, 1), date(2026, 4, 2)])

    def test_snapshot_service_event_risk_returns_conservative_fallback(self) -> None:
        service = MarketMonitorSnapshotService()

        wednesday = service._build_event_risk(date(2026, 4, 15))
        friday = service._build_event_risk(date(2026, 4, 17))

        self.assertTrue(wednesday.index_level.active)
        self.assertEqual(wednesday.index_level.type, "搜索增强缺失-默认收紧")
        self.assertEqual(wednesday.stock_level.earnings_stocks, [])
        self.assertIsNotNone(wednesday.stock_level.rule)
        self.assertFalse(friday.index_level.active)
        self.assertEqual(friday.stock_level.earnings_stocks, [])

    def test_snapshot_service_open_gaps_include_missing_core_series(self) -> None:
        service = MarketMonitorSnapshotService()
        gaps = service._build_open_gaps({"SPY": pd.DataFrame()})

        self.assertIn("缺少 QQQ 日线", gaps)
        self.assertIn("缺少 IWM 日线", gaps)
        self.assertIn("缺少 ^VIX 日线", gaps)
        self.assertIn("缺少未来三日宏观与财报事件原始日历", gaps)


if __name__ == "__main__":
    unittest.main()
