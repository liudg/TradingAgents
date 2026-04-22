import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from tradingagents.web.market_monitor.persistence import MarketMonitorPersistence
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorActionModifier,
    MarketMonitorDataStatusResponse,
    MarketMonitorEvidenceRef,
    MarketMonitorExecutionCard,
    MarketMonitorFactSheet,
    MarketMonitorHistoryPoint,
    MarketMonitorHistoryResponse,
    MarketMonitorIndexEventRisk,
    MarketMonitorLayerMetric,
    MarketMonitorPanicCard,
    MarketMonitorPromptTrace,
    MarketMonitorRunManifest,
    MarketMonitorRunRequest,
    MarketMonitorScoreCard,
    MarketMonitorSignalConfirmation,
    MarketMonitorSnapshotResponse,
    MarketMonitorSourceCoverage,
    MarketMonitorStageResult,
    MarketMonitorStockEventRisk,
    MarketMonitorStyleAssetLayer,
    MarketMonitorStyleEffectiveness,
    MarketMonitorStyleTacticLayer,
    MarketMonitorSystemRiskCard,
    MarketMonitorEventRiskFlag,
)
from tradingagents.web.schemas import JobStatus


class MarketMonitorPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.persistence = MarketMonitorPersistence(Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _build_snapshot(self) -> MarketMonitorSnapshotResponse:
        now = datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)
        fact_sheet = MarketMonitorFactSheet(
            as_of_date=date(2026, 4, 11),
            generated_at=now,
            local_facts={"spy_close": 523.1},
            derived_metrics={"breadth": 63.0},
            open_gaps=["缺少交易所级 breadth 原始数据"],
            source_coverage=MarketMonitorSourceCoverage(
                completeness="medium",
                available_sources=["ETF/指数日线"],
                missing_sources=["交易所级 breadth"],
                degraded=True,
            ),
            evidence_refs=[
                MarketMonitorEvidenceRef(
                    source_type="local_market_data",
                    source_label="SPY 日线",
                    snippet="SPY close 523.1",
                    confidence="high",
                )
            ],
        )
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
            prompt_traces=[
                MarketMonitorPromptTrace(stage="card_inference", card_type="long_term", model="gpt-5.4", parsed_ok=True),
                MarketMonitorPromptTrace(stage="card_inference", card_type="short_term", model="gpt-5.4", parsed_ok=True),
                MarketMonitorPromptTrace(stage="card_inference", card_type="system_risk", model="gpt-5.4", parsed_ok=True),
                MarketMonitorPromptTrace(stage="card_inference", card_type="style", model="gpt-5.4", parsed_ok=True),
                MarketMonitorPromptTrace(stage="card_inference", card_type="event_risk", model="gpt-5.4", parsed_ok=True),
                MarketMonitorPromptTrace(stage="card_inference", card_type="panic", model="gpt-5.4", parsed_ok=True),
                MarketMonitorPromptTrace(stage="execution_aggregation", card_type="execution", model="gpt-5.4", parsed_ok=True),
            ],
            run_id="run-1",
        )

    def test_persistence_round_trip_for_manifest_artifacts_and_traces(self) -> None:
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
            run_id="run-1",
        )
        data_status = MarketMonitorDataStatusResponse(
            timestamp=snapshot.timestamp,
            as_of_date=snapshot.as_of_date,
            source_coverage=snapshot.source_coverage,
            degraded_factors=snapshot.degraded_factors,
            notes=snapshot.notes,
            open_gaps=snapshot.fact_sheet.open_gaps,
            fact_sheet=snapshot.fact_sheet,
            run_id="run-1",
        )
        manifest = MarketMonitorRunManifest(
            run_id="run-1",
            mode="snapshot",
            request=MarketMonitorRunRequest(trigger_endpoint="snapshot", mode="snapshot"),
            status=JobStatus.COMPLETED,
            created_at=snapshot.timestamp,
            started_at=snapshot.timestamp,
            finished_at=snapshot.timestamp,
            results_dir=str(Path(self.temp_dir.name)),
            log_path=str(Path(self.temp_dir.name) / "market_monitor.log"),
            stage_results=[
                MarketMonitorStageResult(stage_name="request_received", status="completed"),
                MarketMonitorStageResult(stage_name="artifact_generation", status="completed"),
            ],
        )
        trace = MarketMonitorPromptTrace(
            stage="card_inference",
            card_type="long_term",
            model="gpt-5.4",
            parsed_ok=True,
            input_summary="SPY/QQQ/IWM facts",
        )

        self.persistence.write_manifest(manifest)
        self.persistence.write_snapshot_artifact(snapshot)
        self.persistence.write_history_artifact(history)
        self.persistence.write_data_status_artifact(data_status)
        self.persistence.write_fact_sheet_artifact(snapshot.fact_sheet)
        self.persistence.write_prompt_trace("card_long_term", trace)
        self.persistence.write_artifact_payload(
            "history_snapshot_2026-04-10",
            snapshot.model_dump(mode="json"),
        )

        restored_manifest = self.persistence.read_manifest()
        restored_snapshot = self.persistence.read_snapshot_artifact()
        restored_history = self.persistence.read_history_artifact()
        restored_data_status = self.persistence.read_data_status_artifact()
        restored_fact_sheet = self.persistence.read_fact_sheet_artifact()
        restored_traces = self.persistence.list_prompt_traces()

        self.assertEqual(restored_manifest.run_id, "run-1")
        self.assertEqual(restored_snapshot.execution_card.regime_label, "黄绿灯-Swing")
        self.assertEqual(restored_history.points[0].regime_label, "黄灯")
        self.assertEqual(restored_data_status.open_gaps[0], "缺少交易所级 breadth 原始数据")
        self.assertEqual(restored_fact_sheet.derived_metrics["breadth"], 63.0)
        self.assertEqual(len(restored_traces), 1)
        self.assertEqual(restored_traces[0].card_type, "long_term")
        self.assertEqual(len(restored_snapshot.prompt_traces), 7)
        self.assertEqual(
            self.persistence.read_artifact_payload("history_snapshot_2026-04-10")["as_of_date"],
            "2026-04-11",
        )


if __name__ == "__main__":
    unittest.main()
