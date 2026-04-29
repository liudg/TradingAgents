import time
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.market_monitor_v231_fixtures import (
    fixture_data_status,
    fixture_history_point,
    fixture_history_response,
    fixture_snapshot,
)
from tradingagents.web.api.app import app, market_monitor_manager
from tradingagents.web.market_monitor.manager import MarketMonitorRunManager
from tradingagents.web.market_monitor.persistence import MarketMonitorPersistence
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorHistoryResponse,
    MarketMonitorRunLlmConfig,
    MarketMonitorRunManifest,
    MarketMonitorRunRequest,
    MarketMonitorStageResult,
)
from tradingagents.web.schemas import JobStatus


class MarketMonitorApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.temp_dir = TemporaryDirectory()
        self.original_runs_root = market_monitor_manager.runs_root
        self.original_runs = market_monitor_manager._runs
        market_monitor_manager.runs_root = Path(self.temp_dir.name)
        market_monitor_manager._runs = {}

    def tearDown(self) -> None:
        for future in list(market_monitor_manager._futures.values()):
            try:
                future.result(timeout=5)
            except Exception:
                pass
        market_monitor_manager.runs_root = self.original_runs_root
        market_monitor_manager._runs = self.original_runs
        self.temp_dir.cleanup()

    def _build_snapshot(self):
        return fixture_snapshot()

    def _wait_for_run(self, run_id: str, expected_status: str = "completed") -> dict:
        deadline = time.monotonic() + 5
        payload: dict | None = None
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/market-monitor/runs/{run_id}")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            if payload["status"] in {"completed", "failed"}:
                self.assertEqual(payload["status"], expected_status)
                return payload
            time.sleep(0.01)
        self.fail(f"market monitor run {run_id} did not reach {expected_status}: {payload}")

    def _wait_for_manager_run(self, manager: MarketMonitorRunManager, run_id: str, expected_status: str = "completed"):
        deadline = time.monotonic() + 5
        detail = None
        while time.monotonic() < deadline:
            detail = manager.get_historical_run(run_id)
            if detail.status in {JobStatus.COMPLETED, JobStatus.FAILED, "completed", "failed"}:
                self.assertEqual(detail.status, expected_status)
                return detail
            time.sleep(0.01)
        self.fail(f"market monitor run {run_id} did not reach {expected_status}: {detail}")

    def _with_data_mode_status(self, payload, data_mode: str, interval: str, includes_prepost: bool):
        input_status = payload.input_data_status.model_copy(update={"interval": interval, "includes_prepost": includes_prepost})
        return payload.model_copy(
            update={"data_mode": data_mode, "data_freshness": "intraday_fresh", "input_data_status": input_status}
        )

    def _assert_data_mode_endpoint(self, endpoint: str, service_method: str, payload, data_mode: str, interval: str, includes_prepost: bool) -> None:
        with patch.object(market_monitor_manager.service, service_method, return_value=payload) as service_mock:
            response = self.client.get(f"{endpoint}?data_mode={data_mode}")
            self.assertEqual(response.status_code, 200)
            detail_payload = self._wait_for_run(response.json()["run_id"])

        response_payload = detail_payload["snapshot"] or detail_payload["data_status"]
        self.assertEqual(response_payload["data_mode"], data_mode)
        self.assertEqual(response_payload["input_data_status"]["interval"], interval)
        self.assertEqual(response_payload["input_data_status"]["includes_prepost"], includes_prepost)
        self.assertEqual(service_mock.call_args.args[0].data_mode, data_mode)

    def test_snapshot_api_starts_background_run_and_persists_v231_payload(self) -> None:
        snapshot = self._build_snapshot()
        with patch.object(market_monitor_manager.service, "get_snapshot", return_value=snapshot):
            response = self.client.get("/api/market-monitor/snapshot")
            self.assertEqual(response.status_code, 200)
            start_payload = response.json()
            self.assertIn(start_payload["status"], {"pending", "running", "completed"})
            run_id = start_payload["run_id"]
            detail_payload = self._wait_for_run(run_id)

        payload = detail_payload["snapshot"]
        self.assertEqual(payload["scorecard_version"], "2.3.1")
        self.assertEqual(payload["data_mode"], "daily")
        self.assertEqual(payload["execution_card"]["regime_label"], "黄绿灯-Swing")
        self.assertEqual(payload["long_term_score"]["zone"], "进攻区")
        self.assertIn("factor_breakdown", payload["long_term_score"])
        self.assertEqual(payload["style_effectiveness"]["tactic_layer"]["top_tactic"], "回调低吸")
        self.assertEqual(payload["fact_sheet"]["derived_metrics"]["breadth_above_200dma_pct"], 63.0)
        self.assertEqual(payload["event_fact_sheet"][0]["event_id"], payload["fact_sheet"]["event_fact_sheet"][0]["event_id"])
        self.assertEqual(len(payload["prompt_traces"]), 1)
        self.assertEqual(payload["run_id"], run_id)

        runs_payload = self.client.get("/api/market-monitor/runs").json()
        self.assertEqual(len(runs_payload), 1)
        self.assertEqual(runs_payload[0]["trigger_endpoint"], "snapshot")
        self.assertTrue(runs_payload[0]["degraded"])

        self.assertEqual(detail_payload["snapshot"]["run_id"], run_id)
        self.assertIsNone(detail_payload["history"])
        self.assertIsNone(detail_payload["data_status"])
        self.assertEqual(len(detail_payload["stage_results"]), 2)

        logs_payload = self.client.get(f"/api/market-monitor/runs/{run_id}/logs").json()
        self.assertTrue(any("Market monitor run" in item["content"] for item in logs_payload))

        traces_payload = self.client.get(f"/api/market-monitor/runs/{run_id}/prompt-traces").json()
        self.assertEqual(traces_payload[0]["card_type"], "long_term")

        fact_sheet_response = self.client.get(f"/api/market-monitor/runs/{run_id}/artifacts/fact_sheet")
        self.assertEqual(fact_sheet_response.status_code, 200)
        self.assertEqual(fact_sheet_response.json()["derived_metrics"]["breadth_above_200dma_pct"], 63.0)
        self.assertEqual(fact_sheet_response.json()["event_fact_sheet"][0]["event_id"], payload["event_fact_sheet"][0]["event_id"])

    def test_market_monitor_artifact_api_rejects_unsupported_artifact(self) -> None:
        with patch.object(market_monitor_manager.service, "get_snapshot", return_value=self._build_snapshot()):
            response = self.client.get("/api/market-monitor/snapshot")
            self.assertEqual(response.status_code, 200)
            run_id = response.json()["run_id"]
            self._wait_for_run(run_id)

        invalid_response = self.client.get(f"/api/market-monitor/runs/{run_id}/artifacts/not_supported")
        self.assertEqual(invalid_response.status_code, 400)

    def test_history_run_persists_replay_artifacts_and_traces(self) -> None:
        snapshot = self._build_snapshot()
        history = MarketMonitorHistoryResponse(
            as_of_date=date(2026, 4, 11),
            points=[
                fixture_history_point(date(2026, 4, 10)),
                fixture_history_point(date(2026, 4, 11)).model_copy(update={"regime_label": "黄绿灯-Swing"}),
            ],
        )
        with patch.object(
            market_monitor_manager.service,
            "resolve_history_trade_dates",
            return_value=[date(2026, 4, 10), date(2026, 4, 11)],
        ), patch.object(
            market_monitor_manager.service,
            "get_history_snapshots",
            return_value=[
                snapshot.model_copy(update={"as_of_date": date(2026, 4, 10)}),
                snapshot.model_copy(update={"as_of_date": date(2026, 4, 11)}),
            ],
        ), patch.object(market_monitor_manager.service, "build_history_response", return_value=history):
            response = self.client.get("/api/market-monitor/history?days=2")
            self.assertEqual(response.status_code, 200)
            run_id = response.json()["run_id"]
            detail_payload = self._wait_for_run(run_id)

        self.assertEqual(detail_payload["status"], "completed")
        self.assertEqual(len(detail_payload["prompt_traces"]), 2)
        self.assertEqual(detail_payload["stage_results"][1]["stage_name"], "history_materialization")
        artifact_response = self.client.get(f"/api/market-monitor/runs/{run_id}/artifacts/history_snapshot_2026-04-10")
        self.assertEqual(artifact_response.status_code, 200)
        self.assertEqual(artifact_response.json()["as_of_date"], "2026-04-10")

    def test_history_run_can_be_recovered_from_interrupted_manifest(self) -> None:
        run_id = "run-recover-history"
        run_dir = Path(self.temp_dir.name) / "2026-04-11" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        persistence = MarketMonitorPersistence(run_dir)
        manifest = MarketMonitorRunManifest(
            run_id=run_id,
            mode="history",
            request=MarketMonitorRunRequest(
                trigger_endpoint="history",
                as_of_date=date(2026, 4, 11),
                days=2,
                force_refresh=False,
                mode="history",
            ),
            status=JobStatus.RUNNING,
            created_at=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
            started_at=datetime(2026, 4, 12, 9, 31, 0, tzinfo=timezone.utc),
            results_dir=str(run_dir),
            log_path=str(run_dir / "market_monitor.log"),
            stage_results=[
                MarketMonitorStageResult(stage_name="request_received", status="completed"),
                MarketMonitorStageResult(stage_name="history_materialization", status="running"),
                MarketMonitorStageResult(stage_name="artifact_generation", status="pending"),
            ],
        )
        persistence.write_manifest(manifest)

        restored_manager = MarketMonitorRunManager(runs_root=Path(self.temp_dir.name), service=market_monitor_manager.service)
        market_monitor_manager._runs = dict(restored_manager._runs)
        restored_detail = restored_manager.get_historical_run(run_id)
        self.assertEqual(restored_detail.status, "failed")
        self.assertTrue(restored_detail.recoverable)

        snapshot = self._build_snapshot()
        recovered_history = fixture_history_response()
        with patch.object(market_monitor_manager.service, "resolve_history_trade_dates", return_value=[date(2026, 4, 10)]), patch.object(
            market_monitor_manager.service,
            "get_history_snapshots",
            return_value=[snapshot.model_copy(update={"as_of_date": date(2026, 4, 10)})],
        ), patch.object(market_monitor_manager.service, "build_history_response", return_value=recovered_history):
            recovered_response = self.client.post(f"/api/market-monitor/runs/{run_id}/recover")
            self.assertEqual(recovered_response.status_code, 200)
            self.assertIn(recovered_response.json()["status"], {"pending", "running", "completed"})
            recovered_payload = self._wait_for_run(run_id)

        self.assertIsNotNone(recovered_payload["history"])
        self.assertEqual(recovered_payload["history"]["points"][0]["panic_state"], "无信号")

    def test_history_api_rejects_intraday_data_mode(self) -> None:
        response = self.client.get("/api/market-monitor/history?data_mode=intraday_realtime")

        self.assertEqual(response.status_code, 422)
        self.assertIn("daily", response.json()["detail"])

    def test_history_api_returns_points_after_background_run(self) -> None:
        history = fixture_history_response()
        snapshot = self._build_snapshot()
        with patch.object(market_monitor_manager.service, "resolve_history_trade_dates", return_value=[date(2026, 4, 10)]), patch.object(
            market_monitor_manager.service,
            "get_history_snapshots",
            return_value=[snapshot.model_copy(update={"as_of_date": date(2026, 4, 10)})],
        ), patch.object(market_monitor_manager.service, "build_history_response", return_value=history):
            response = self.client.get("/api/market-monitor/history?days=20")
            self.assertEqual(response.status_code, 200)
            detail = self._wait_for_run(response.json()["run_id"])

        self.assertEqual(detail["history"]["points"][0]["regime_label"], "黄灯")
        self.assertEqual(detail["history"]["points"][0]["panic_state"], "无信号")

    def test_data_status_api_returns_v231_data_status_after_background_run(self) -> None:
        snapshot = self._build_snapshot()
        data_status = fixture_data_status(fact_sheet=snapshot.fact_sheet).model_copy(update={"event_fact_sheet": snapshot.event_fact_sheet})
        with patch.object(market_monitor_manager.service, "get_data_status", return_value=data_status):
            response = self.client.get("/api/market-monitor/data-status")
            self.assertEqual(response.status_code, 200)
            detail = self._wait_for_run(response.json()["run_id"])

        payload = detail["data_status"]
        self.assertEqual(payload["data_mode"], "daily")
        self.assertEqual(payload["input_data_status"]["source"], "yfinance")
        self.assertIn("缺少交易所级 breadth 原始数据", payload["open_gaps"])
        self.assertEqual(payload["event_fact_sheet"][0]["event_id"], payload["fact_sheet"]["event_fact_sheet"][0]["event_id"])
        self.assertIsNotNone(payload["fact_sheet"])

    def test_snapshot_api_accepts_intraday_data_modes(self) -> None:
        for data_mode, interval, includes_prepost in (
            ("intraday_delayed", "5m", False),
            ("intraday_realtime", "1m", True),
        ):
            with self.subTest(data_mode=data_mode):
                snapshot = self._with_data_mode_status(self._build_snapshot(), data_mode, interval, includes_prepost)
                self._assert_data_mode_endpoint(
                    "/api/market-monitor/snapshot",
                    "get_snapshot",
                    snapshot,
                    data_mode,
                    interval,
                    includes_prepost,
                )

    def test_snapshot_api_passes_force_refresh_flag(self) -> None:
        with patch.object(market_monitor_manager.service, "get_snapshot", return_value=self._build_snapshot()) as service_mock:
            response = self.client.get("/api/market-monitor/snapshot?force_refresh=true")
            self.assertEqual(response.status_code, 200)
            self._wait_for_run(response.json()["run_id"])

        request = service_mock.call_args.args[0]
        self.assertTrue(request.force_refresh)

    def test_snapshot_api_does_not_require_history_or_data_status(self) -> None:
        with patch.object(market_monitor_manager.service, "get_snapshot", return_value=self._build_snapshot()) as snapshot_mock, patch.object(
            market_monitor_manager.service,
            "get_history",
            side_effect=AssertionError("history should not be called"),
        ) as history_mock, patch.object(
            market_monitor_manager.service,
            "get_data_status",
            side_effect=AssertionError("data status should not be called"),
        ) as data_status_mock:
            response = self.client.get("/api/market-monitor/snapshot")
            self.assertEqual(response.status_code, 200)
            detail_payload = self._wait_for_run(response.json()["run_id"])

        self.assertEqual(snapshot_mock.call_count, 1)
        self.assertEqual(history_mock.call_count, 0)
        self.assertEqual(data_status_mock.call_count, 0)
        self.assertIsNotNone(detail_payload["snapshot"])
        self.assertIsNone(detail_payload["history"])
        self.assertIsNone(detail_payload["data_status"])

    def test_history_api_passes_force_refresh_flag(self) -> None:
        history = MarketMonitorHistoryResponse(as_of_date=date(2026, 4, 11), points=[])
        with patch.object(market_monitor_manager.service, "resolve_history_trade_dates", return_value=[]) as resolve_mock, patch.object(
            market_monitor_manager.service,
            "get_history_snapshots",
            return_value=[],
        ) as snapshots_mock, patch.object(market_monitor_manager.service, "build_history_response", return_value=history) as build_mock:
            response = self.client.get("/api/market-monitor/history?days=20&force_refresh=true")
            self.assertEqual(response.status_code, 200)
            self._wait_for_run(response.json()["run_id"])

        request = resolve_mock.call_args.args[0]
        self.assertTrue(request.force_refresh)
        self.assertEqual(snapshots_mock.call_count, 1)
        self.assertEqual(build_mock.call_count, 1)

    def test_data_status_api_accepts_intraday_data_modes(self) -> None:
        for data_mode, interval, includes_prepost in (
            ("intraday_delayed", "5m", False),
            ("intraday_realtime", "1m", True),
        ):
            with self.subTest(data_mode=data_mode):
                data_status = self._with_data_mode_status(fixture_data_status(), data_mode, interval, includes_prepost)
                self._assert_data_mode_endpoint(
                    "/api/market-monitor/data-status",
                    "get_data_status",
                    data_status,
                    data_mode,
                    interval,
                    includes_prepost,
                )

    def test_data_status_api_passes_force_refresh_flag(self) -> None:
        with patch.object(market_monitor_manager.service, "get_data_status", return_value=fixture_data_status()) as service_mock:
            response = self.client.get("/api/market-monitor/data-status?force_refresh=true")
            self.assertEqual(response.status_code, 200)
            self._wait_for_run(response.json()["run_id"])

        request = service_mock.call_args.args[0]
        self.assertTrue(request.force_refresh)

    def test_data_status_api_does_not_require_snapshot_or_history(self) -> None:
        with patch.object(market_monitor_manager.service, "get_data_status", return_value=fixture_data_status()) as data_status_mock, patch.object(
            market_monitor_manager.service,
            "get_snapshot",
            side_effect=AssertionError("snapshot should not be called"),
        ) as snapshot_mock, patch.object(
            market_monitor_manager.service,
            "get_history",
            side_effect=AssertionError("history should not be called"),
        ) as history_mock:
            response = self.client.get("/api/market-monitor/data-status")
            self.assertEqual(response.status_code, 200)
            self._wait_for_run(response.json()["run_id"])

        self.assertEqual(data_status_mock.call_count, 1)
        self.assertEqual(snapshot_mock.call_count, 0)
        self.assertEqual(history_mock.call_count, 0)

    def test_run_manager_default_service_enables_llm_for_web_endpoints(self) -> None:
        with patch("tradingagents.web.market_monitor.manager.MarketMonitorSnapshotService") as service_cls:
            MarketMonitorRunManager(runs_root=Path(self.temp_dir.name))

        service_cls.assert_called_once_with()

    def test_run_manager_uses_llm_config_for_snapshot_runs(self) -> None:
        manager = MarketMonitorRunManager(runs_root=Path(self.temp_dir.name))
        request = MarketMonitorRunRequest(
            trigger_endpoint="snapshot",
            as_of_date=date(2026, 4, 11),
            force_refresh=False,
            mode="snapshot",
            llm_config=MarketMonitorRunLlmConfig(provider="anthropic", model="claude-sonnet-4-6", reasoning_effort="medium"),
        )
        snapshot = self._build_snapshot()

        with patch("tradingagents.web.market_monitor.manager.MarketMonitorSnapshotService") as service_cls:
            service = service_cls.return_value
            service.get_snapshot.return_value = snapshot
            run_id, result, history, data_status = manager._execute_run(request)

        service_cls.assert_called_once_with(llm_config=request.llm_config)
        service.get_snapshot.assert_called_once()
        self.assertTrue(run_id)
        self.assertIsNotNone(result)
        self.assertIsNone(history)
        self.assertIsNone(data_status)

    def test_create_run_api_rejects_debug_card_endpoint(self) -> None:
        response = self.client.post(
            "/api/market-monitor/runs",
            json={"trigger_endpoint": "debug_card", "mode": "debug_card", "force_refresh": False},
        )
        self.assertEqual(response.status_code, 422)

    def test_create_run_returns_the_newly_created_run_instead_of_latest_existing_run(self) -> None:
        manager = MarketMonitorRunManager(runs_root=Path(self.temp_dir.name), service=market_monitor_manager.service)
        existing_snapshot = self._build_snapshot()
        manager._runs["existing-run"] = {
            "run_id": "existing-run",
            "request": MarketMonitorRunRequest(trigger_endpoint="snapshot", as_of_date=date(2026, 4, 11), force_refresh=False, mode="snapshot"),
            "status": "completed",
            "snapshot": existing_snapshot,
            "history": None,
            "data_status": None,
            "fact_sheet": existing_snapshot.fact_sheet,
            "manifest": None,
            "stage_results": [],
            "prompt_traces": list(existing_snapshot.prompt_traces),
            "error_message": None,
            "log_path": str(Path(self.temp_dir.name) / "existing-run.log"),
            "results_dir": str(Path(self.temp_dir.name) / "2026-04-11" / "existing-run"),
            "created_at": datetime(2026, 4, 12, 10, 0, 0),
            "started_at": datetime(2026, 4, 12, 10, 0, 1),
            "finished_at": datetime(2026, 4, 12, 10, 0, 2),
        }
        request = MarketMonitorRunRequest(trigger_endpoint="snapshot", as_of_date=date(2026, 4, 10), force_refresh=False, mode="snapshot")

        with patch.object(market_monitor_manager.service, "get_snapshot", return_value=self._build_snapshot().model_copy(update={"as_of_date": date(2026, 4, 10), "prompt_traces": []})):
            created = manager.create_run(request)
            detail = self._wait_for_manager_run(manager, created.run_id)

        self.assertNotEqual(created.run_id, "existing-run")
        self.assertEqual(detail.run_id, created.run_id)
        self.assertEqual(detail.snapshot.as_of_date, date(2026, 4, 10))

    def test_run_manager_uses_llm_config_when_recovering_snapshot_runs(self) -> None:
        manager = MarketMonitorRunManager(runs_root=Path(self.temp_dir.name))
        run_id = "run-recover-snapshot"
        run_dir = Path(self.temp_dir.name) / "2026-04-11" / run_id
        persistence = MarketMonitorPersistence(run_dir)
        request = MarketMonitorRunRequest(
            trigger_endpoint="snapshot",
            as_of_date=date(2026, 4, 11),
            force_refresh=False,
            mode="snapshot",
            llm_config=MarketMonitorRunLlmConfig(provider="anthropic", model="claude-sonnet-4-6", reasoning_effort="medium"),
        )
        manifest = MarketMonitorRunManifest(
            run_id=run_id,
            mode="snapshot",
            request=request,
            status="failed",
            created_at=datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc),
            started_at=datetime(2026, 4, 12, 9, 31, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 4, 12, 9, 32, 0, tzinfo=timezone.utc),
            results_dir=str(run_dir),
            log_path=str(run_dir / "market_monitor.log"),
            recoverable=True,
            stage_results=[
                MarketMonitorStageResult(stage_name="request_received", status="completed"),
                MarketMonitorStageResult(stage_name="artifact_generation", status="failed"),
            ],
        )
        persistence.write_manifest(manifest)
        manager._runs[run_id] = {
            "run_id": run_id,
            "request": request,
            "status": "failed",
            "snapshot": None,
            "history": None,
            "data_status": None,
            "fact_sheet": None,
            "manifest": manifest,
            "stage_results": manifest.stage_results,
            "prompt_traces": [],
            "error_message": "interrupted",
            "log_path": str(run_dir / "market_monitor.log"),
            "results_dir": str(run_dir),
            "created_at": manifest.created_at,
            "started_at": manifest.started_at,
            "finished_at": manifest.finished_at,
        }

        with patch("tradingagents.web.market_monitor.manager.MarketMonitorSnapshotService") as service_cls:
            service = service_cls.return_value
            service.get_snapshot.return_value = self._build_snapshot()
            queued_detail = manager.recover_run(run_id)
            detail = self._wait_for_manager_run(manager, queued_detail.run_id)

        service_cls.assert_called_once_with(llm_config=request.llm_config)
        service.get_snapshot.assert_called_once()
        self.assertEqual(detail.status, "completed")
        self.assertEqual(detail.snapshot.run_id, run_id)

    def test_run_manager_restores_persisted_runs(self) -> None:
        snapshot = self._build_snapshot()
        with patch.object(market_monitor_manager.service, "get_snapshot", return_value=snapshot):
            response = self.client.get("/api/market-monitor/snapshot")
            self.assertEqual(response.status_code, 200)
            run_id = response.json()["run_id"]
            self._wait_for_run(run_id)

        restored_manager = MarketMonitorRunManager(runs_root=Path(self.temp_dir.name), service=market_monitor_manager.service)
        restored_runs = restored_manager.list_historical_runs()
        self.assertEqual(len(restored_runs), 1)
        self.assertEqual(restored_runs[0].run_id, run_id)

        restored_detail = restored_manager.get_historical_run(run_id)
        self.assertEqual(restored_detail.snapshot.run_id, run_id)
        self.assertIsNone(restored_detail.history)
        self.assertIsNone(restored_detail.data_status)
        self.assertIsNotNone(restored_detail.manifest)
        self.assertEqual(len(restored_detail.stage_results), 2)

    def test_failed_run_is_persisted_and_listed(self) -> None:
        with patch.object(market_monitor_manager.service, "get_snapshot", side_effect=RuntimeError("snapshot boom")):
            response = self.client.get("/api/market-monitor/snapshot")
            self.assertEqual(response.status_code, 200)
            run_id = response.json()["run_id"]
            detail_payload = self._wait_for_run(run_id, expected_status="failed")

        runs_payload = self.client.get("/api/market-monitor/runs").json()
        self.assertEqual(len(runs_payload), 1)
        self.assertEqual(runs_payload[0]["status"], "failed")
        self.assertEqual(runs_payload[0]["error_message"], "snapshot boom")

        self.assertIsNone(detail_payload["snapshot"])
        self.assertEqual(detail_payload["error_message"], "snapshot boom")
        self.assertTrue(detail_payload["recoverable"])
        self.assertIsNotNone(detail_payload["manifest"])

    def test_llm_initialization_failure_marks_background_run_failed(self) -> None:
        response = self.client.post(
            "/api/market-monitor/runs",
            json={
                "trigger_endpoint": "snapshot",
                "as_of_date": "2026-04-11",
                "force_refresh": False,
                "mode": "snapshot",
                "llm_config": {"provider": "not-a-provider", "model": "test-model"},
            },
        )
        self.assertEqual(response.status_code, 200)
        run_id = response.json()["run_id"]

        detail_payload = self._wait_for_run(run_id, expected_status="failed")

        self.assertIsNone(detail_payload["snapshot"])
        self.assertIn("Unsupported LLM provider", detail_payload["error_message"])
        self.assertTrue(detail_payload["recoverable"])
        self.assertEqual(detail_payload["stage_results"][-1]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
