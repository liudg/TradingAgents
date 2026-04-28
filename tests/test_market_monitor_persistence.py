import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.market_monitor_v231_fixtures import (
    fixture_data_status,
    fixture_history_response,
    fixture_snapshot,
)
from tradingagents.web.market_monitor.persistence import MarketMonitorPersistence
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorPromptTrace,
    MarketMonitorRunManifest,
    MarketMonitorRunRequest,
    MarketMonitorStageResult,
)
from tradingagents.web.schemas import JobStatus


class MarketMonitorPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.persistence = MarketMonitorPersistence(Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_persistence_round_trip_for_manifest_artifacts_and_traces(self) -> None:
        snapshot = fixture_snapshot()
        history = fixture_history_response()
        data_status = fixture_data_status(fact_sheet=snapshot.fact_sheet)
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
            stage="card_judgment",
            card_type="long_term",
            model="gpt-5.4",
            parsed_ok=True,
            input_summary="SPY/QQQ/IWM deterministic facts",
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
        self.assertEqual(restored_snapshot.scorecard_version, "2.3.1")
        self.assertEqual(restored_snapshot.execution_card.regime_label, "黄绿灯-Swing")
        self.assertEqual(restored_history.points[0].panic_state, "无信号")
        self.assertEqual(restored_data_status.data_mode, "daily")
        self.assertEqual(restored_data_status.open_gaps[0], "缺少交易所级 breadth 原始数据")
        self.assertEqual(restored_fact_sheet.derived_metrics["breadth_above_200dma_pct"], 63.0)
        self.assertEqual(len(restored_traces), 1)
        self.assertEqual(restored_traces[0].card_type, "long_term")
        self.assertEqual(len(restored_snapshot.prompt_traces), 1)
        self.assertEqual(
            self.persistence.read_artifact_payload("history_snapshot_2026-04-10")["as_of_date"],
            "2026-04-11",
        )


if __name__ == "__main__":
    unittest.main()
