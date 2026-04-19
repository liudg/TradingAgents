import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from tradingagents.web.api.app import app, market_monitor_manager
from tradingagents.web.market_monitor.manager import MarketMonitorRunManager
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorActionModifier,
    MarketMonitorDataStatusResponse,
    MarketMonitorEventRiskFlag,
    MarketMonitorExecutionCard,
    MarketMonitorHistoryPoint,
    MarketMonitorHistoryResponse,
    MarketMonitorIndexEventRisk,
    MarketMonitorLayerMetric,
    MarketMonitorPanicCard,
    MarketMonitorScoreCard,
    MarketMonitorSignalConfirmation,
    MarketMonitorSnapshotResponse,
    MarketMonitorSourceCoverage,
    MarketMonitorStockEventRisk,
    MarketMonitorStyleAssetLayer,
    MarketMonitorStyleEffectiveness,
    MarketMonitorStyleTacticLayer,
    MarketMonitorSystemRiskCard,
)


class MarketMonitorApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.temp_dir = TemporaryDirectory()
        self.original_runs_root = market_monitor_manager.runs_root
        self.original_runs = market_monitor_manager._runs
        market_monitor_manager.runs_root = Path(self.temp_dir.name)
        market_monitor_manager._runs = {}

    def tearDown(self) -> None:
        market_monitor_manager.runs_root = self.original_runs_root
        market_monitor_manager._runs = self.original_runs
        self.temp_dir.cleanup()

    def _build_snapshot(self) -> MarketMonitorSnapshotResponse:
        now = datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)
        event_risk = MarketMonitorEventRiskFlag(
            index_level=MarketMonitorIndexEventRisk(
                active=True,
                type="宏观窗口",
                days_to_event=1,
                action_modifier=MarketMonitorActionModifier(note="减少追高。"),
            ),
            stock_level=MarketMonitorStockEventRisk(
                earnings_stocks=["NVDA"],
                rule="财报股单票上限减半。",
            ),
        )
        return MarketMonitorSnapshotResponse(
            timestamp=now,
            as_of_date=date(2026, 4, 11),
            data_freshness="delayed_15min",
            long_term_score=MarketMonitorScoreCard(
                score=68.5,
                zone="进攻区",
                delta_1d=2.1,
                delta_5d=8.2,
                slope_state="缓慢改善",
                summary="长线环境偏多。",
                action="建议维持趋势仓。",
                recommended_exposure="60%-80%",
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
                pcr_percentile=None,
                pcr_absolute=None,
                pcr_panic_flag=None,
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
                    current_regime_days=1,
                    downgrade_unlock_in_days=2,
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
                reversal_confirmation_score=39.0,
                action="加入观察列表，等待确认。",
                system_risk_override=None,
                stop_loss="ATR×1.0",
                profit_rule="达 1R 兑现 50%，余仓移止损到成本线。",
                timeout_warning=False,
                days_held=0,
                early_entry_allowed=False,
                max_position_hint="20%-35%",
            ),
            event_risk_flag=event_risk,
            source_coverage=MarketMonitorSourceCoverage(
                completeness="medium",
                available_sources=["ETF/指数日线", "VIX 日线", "本地缓存"],
                missing_sources=["交易所级 breadth"],
                degraded=True,
            ),
            degraded_factors=["广度因子使用 ETF 代理池近似"],
            notes=["已按代理池与降级规则输出结果。"],
        )

    def test_snapshot_api_returns_formal_market_monitor_payload(self) -> None:
        snapshot = self._build_snapshot()
        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_snapshot",
            return_value=snapshot,
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_history",
            return_value=MarketMonitorHistoryResponse(as_of_date=date(2026, 4, 11), points=[]),
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_data_status",
            return_value=MarketMonitorDataStatusResponse(
                timestamp=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
                as_of_date=date(2026, 4, 11),
                source_coverage=snapshot.source_coverage,
                degraded_factors=snapshot.degraded_factors,
                notes=snapshot.notes,
                open_gaps=[],
            ),
        ):
            response = self.client.get("/api/market-monitor/snapshot")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["execution_card"]["regime_label"], "黄绿灯-Swing")
        self.assertEqual(payload["long_term_score"]["zone"], "进攻区")
        self.assertEqual(payload["style_effectiveness"]["tactic_layer"]["top_tactic"], "回调低吸")
        self.assertTrue(payload["run_id"])

        runs_response = self.client.get("/api/market-monitor/runs")
        self.assertEqual(runs_response.status_code, 200)
        runs_payload = runs_response.json()
        self.assertEqual(len(runs_payload), 1)
        self.assertEqual(runs_payload[0]["run_id"], payload["run_id"])
        self.assertEqual(runs_payload[0]["trigger_endpoint"], "snapshot")

        detail_response = self.client.get(f"/api/market-monitor/runs/{payload['run_id']}")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        self.assertEqual(detail_payload["snapshot"]["run_id"], payload["run_id"])
        self.assertIsNone(detail_payload["history"])
        self.assertIsNone(detail_payload["data_status"])

        logs_response = self.client.get(f"/api/market-monitor/runs/{payload['run_id']}/logs")
        self.assertEqual(logs_response.status_code, 200)
        logs_payload = logs_response.json()
        self.assertTrue(any("Market monitor run" in item["content"] for item in logs_payload))

    def test_history_api_returns_points(self) -> None:
        history = MarketMonitorHistoryResponse(
            as_of_date=date(2026, 4, 11),
            points=[
                MarketMonitorHistoryPoint(
                    trade_date=date(2026, 4, 10),
                    long_term_score=64.0,
                    short_term_score=58.0,
                    system_risk_score=36.0,
                    panic_score=22.0,
                    regime_label="黄灯",
                )
            ],
        )
        snapshot = self._build_snapshot()
        data_status = MarketMonitorDataStatusResponse(
            timestamp=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
            as_of_date=date(2026, 4, 11),
            source_coverage=snapshot.source_coverage,
            degraded_factors=snapshot.degraded_factors,
            notes=snapshot.notes,
            open_gaps=[],
        )
        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_history",
            return_value=history,
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_snapshot",
            return_value=snapshot,
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_data_status",
            return_value=data_status,
        ):
            response = self.client.get("/api/market-monitor/history?days=20")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["points"][0]["regime_label"], "黄灯")

    def test_data_status_api_returns_coverage(self) -> None:
        data_status = MarketMonitorDataStatusResponse(
            timestamp=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
            as_of_date=date(2026, 4, 11),
            source_coverage=MarketMonitorSourceCoverage(
                completeness="medium",
                available_sources=["ETF/指数日线"],
                missing_sources=["交易所级 breadth"],
                degraded=True,
            ),
            degraded_factors=["广度因子使用 ETF 代理池近似"],
            notes=["已按代理池与降级规则输出结果。"],
            open_gaps=["缺少交易所级 breadth 原始数据"],
        )
        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_data_status",
            return_value=data_status,
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_snapshot",
            return_value=self._build_snapshot(),
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_history",
            return_value=MarketMonitorHistoryResponse(as_of_date=date(2026, 4, 11), points=[]),
        ):
            response = self.client.get("/api/market-monitor/data-status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source_coverage"]["completeness"], "medium")
        self.assertIn("缺少交易所级 breadth 原始数据", payload["open_gaps"])

    def test_snapshot_api_passes_force_refresh_flag(self) -> None:
        snapshot = self._build_snapshot()
        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_snapshot",
            return_value=snapshot,
        ) as service_mock:
            response = self.client.get("/api/market-monitor/snapshot?force_refresh=true")

        self.assertEqual(response.status_code, 200)
        request = service_mock.call_args.args[0]
        self.assertTrue(request.force_refresh)

    def test_snapshot_api_does_not_require_history_or_data_status(self) -> None:
        snapshot = self._build_snapshot()
        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_snapshot",
            return_value=snapshot,
        ) as snapshot_mock, patch(
            "tradingagents.web.api.app.market_monitor_service.get_history",
            side_effect=AssertionError("history should not be called"),
        ) as history_mock, patch(
            "tradingagents.web.api.app.market_monitor_service.get_data_status",
            side_effect=AssertionError("data status should not be called"),
        ) as data_status_mock:
            response = self.client.get("/api/market-monitor/snapshot")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(snapshot_mock.call_count, 1)
        self.assertEqual(history_mock.call_count, 0)
        self.assertEqual(data_status_mock.call_count, 0)
        detail_payload = self.client.get(f"/api/market-monitor/runs/{response.json()['run_id']}").json()
        self.assertIsNotNone(detail_payload["snapshot"])
        self.assertIsNone(detail_payload["history"])
        self.assertIsNone(detail_payload["data_status"])

    def test_history_api_passes_force_refresh_flag(self) -> None:
        history = MarketMonitorHistoryResponse(as_of_date=date(2026, 4, 11), points=[])
        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_history",
            return_value=history,
        ) as service_mock:
            response = self.client.get("/api/market-monitor/history?days=20&force_refresh=true")

        self.assertEqual(response.status_code, 200)
        request = service_mock.call_args.args[0]
        self.assertTrue(request.force_refresh)

    def test_history_api_does_not_require_snapshot_or_data_status(self) -> None:
        history = MarketMonitorHistoryResponse(as_of_date=date(2026, 4, 11), points=[])
        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_history",
            return_value=history,
        ) as history_mock, patch(
            "tradingagents.web.api.app.market_monitor_service.get_snapshot",
            side_effect=AssertionError("snapshot should not be called"),
        ) as snapshot_mock, patch(
            "tradingagents.web.api.app.market_monitor_service.get_data_status",
            side_effect=AssertionError("data status should not be called"),
        ) as data_status_mock:
            response = self.client.get("/api/market-monitor/history?days=20")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(history_mock.call_count, 1)
        self.assertEqual(snapshot_mock.call_count, 0)
        self.assertEqual(data_status_mock.call_count, 0)

    def test_data_status_api_passes_force_refresh_flag(self) -> None:
        data_status = MarketMonitorDataStatusResponse(
            timestamp=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
            as_of_date=date(2026, 4, 11),
            source_coverage=MarketMonitorSourceCoverage(
                completeness="medium",
                available_sources=["ETF/指数日线"],
                missing_sources=["交易所级 breadth"],
                degraded=True,
            ),
            degraded_factors=["广度因子使用 ETF 代理池近似"],
            notes=["已按代理池与降级规则输出结果。"],
            open_gaps=["缺少交易所级 breadth 原始数据"],
        )
        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_data_status",
            return_value=data_status,
        ) as service_mock:
            response = self.client.get("/api/market-monitor/data-status?force_refresh=true")

        self.assertEqual(response.status_code, 200)
        request = service_mock.call_args.args[0]
        self.assertTrue(request.force_refresh)

    def test_data_status_api_does_not_require_snapshot_or_history(self) -> None:
        data_status = MarketMonitorDataStatusResponse(
            timestamp=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
            as_of_date=date(2026, 4, 11),
            source_coverage=MarketMonitorSourceCoverage(
                completeness="medium",
                available_sources=["ETF/指数日线"],
                missing_sources=["交易所级 breadth"],
                degraded=True,
            ),
            degraded_factors=["广度因子使用 ETF 代理池近似"],
            notes=["已按代理池与降级规则输出结果。"],
            open_gaps=["缺少交易所级 breadth 原始数据"],
        )
        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_data_status",
            return_value=data_status,
        ) as data_status_mock, patch(
            "tradingagents.web.api.app.market_monitor_service.get_snapshot",
            side_effect=AssertionError("snapshot should not be called"),
        ) as snapshot_mock, patch(
            "tradingagents.web.api.app.market_monitor_service.get_history",
            side_effect=AssertionError("history should not be called"),
        ) as history_mock:
            response = self.client.get("/api/market-monitor/data-status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(data_status_mock.call_count, 1)
        self.assertEqual(snapshot_mock.call_count, 0)
        self.assertEqual(history_mock.call_count, 0)

    def test_run_manager_restores_persisted_runs(self) -> None:
        snapshot = self._build_snapshot()
        history = MarketMonitorHistoryResponse(
            as_of_date=date(2026, 4, 11),
            points=[
                MarketMonitorHistoryPoint(
                    trade_date=date(2026, 4, 10),
                    long_term_score=64.0,
                    short_term_score=58.0,
                    system_risk_score=36.0,
                    panic_score=22.0,
                    regime_label="黄灯",
                )
            ],
        )
        data_status = MarketMonitorDataStatusResponse(
            timestamp=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
            as_of_date=date(2026, 4, 11),
            source_coverage=snapshot.source_coverage,
            degraded_factors=snapshot.degraded_factors,
            notes=snapshot.notes,
            open_gaps=["缺少交易所级 breadth 原始数据"],
        )
        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_snapshot",
            return_value=snapshot,
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_history",
            return_value=history,
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_data_status",
            return_value=data_status,
        ):
            response = self.client.get("/api/market-monitor/snapshot")

        self.assertEqual(response.status_code, 200)
        run_id = response.json()["run_id"]

        restored_manager = MarketMonitorRunManager(
            runs_root=Path(self.temp_dir.name),
            service=market_monitor_manager.service,
        )
        restored_runs = restored_manager.list_historical_runs()
        self.assertEqual(len(restored_runs), 1)
        self.assertEqual(restored_runs[0].run_id, run_id)

        restored_detail = restored_manager.get_historical_run(run_id)
        self.assertEqual(restored_detail.snapshot.run_id, run_id)
        self.assertIsNone(restored_detail.history)
        self.assertIsNone(restored_detail.data_status)

    def test_failed_run_is_persisted_and_listed(self) -> None:
        failing_client = TestClient(app, raise_server_exceptions=False)
        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_snapshot",
            side_effect=RuntimeError("snapshot boom"),
        ):
            response = failing_client.get("/api/market-monitor/snapshot")

        self.assertEqual(response.status_code, 500)

        runs_response = self.client.get("/api/market-monitor/runs")
        self.assertEqual(runs_response.status_code, 200)
        runs_payload = runs_response.json()
        self.assertEqual(len(runs_payload), 1)
        self.assertEqual(runs_payload[0]["status"], "failed")
        self.assertEqual(runs_payload[0]["error_message"], "snapshot boom")

        run_id = runs_payload[0]["run_id"]
        detail_response = self.client.get(f"/api/market-monitor/runs/{run_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        self.assertIsNone(detail_payload["snapshot"])
        self.assertEqual(detail_payload["error_message"], "snapshot boom")

        logs_response = self.client.get(f"/api/market-monitor/runs/{run_id}/logs")
        self.assertEqual(logs_response.status_code, 200)
        logs_payload = logs_response.json()
        self.assertTrue(any(item["level"] == "Error" for item in logs_payload))
        self.assertTrue(any("snapshot boom" in item["content"] for item in logs_payload))


if __name__ == "__main__":
    unittest.main()
