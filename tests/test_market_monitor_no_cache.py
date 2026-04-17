import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from tradingagents.web.market_monitor.errors import MarketMonitorCorruptedStateError
from tradingagents.web.market_monitor.prompt_store import PromptCaptureStore
from tradingagents.web.market_monitor.run_store import MonitorRunStore


class PromptCaptureStoreTests(unittest.TestCase):
    def test_capture_prompt_writes_complete_payload_to_independent_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = PromptCaptureStore(Path(temp_dir))

            prompt = store.capture_prompt(
                run_id="run-1",
                stage_key="judgment_group_a",
                attempt=1,
                model="gpt-5.4",
                payload={
                    "instructions": "你是市场监控裁决器。",
                    "input": {"as_of_date": date(2026, 4, 11).isoformat()},
                    "schema": {"type": "object"},
                    "tools": [{"type": "web_search"}],
                },
            )

            self.assertEqual(prompt.stage_key, "judgment_group_a")
            self.assertTrue(prompt.file_path.endswith(".json"))
            saved = json.loads(Path(prompt.file_path).read_text(encoding="utf-8"))
            self.assertEqual(saved["run_id"], "run-1")
            self.assertEqual(saved["stage_key"], "judgment_group_a")
            self.assertEqual(saved["attempt"], 1)
            self.assertEqual(saved["model"], "gpt-5.4")
            self.assertEqual(saved["request_status"], "captured")
            self.assertIsNone(saved["request_error"])
            self.assertIn("status_updated_at", saved)
            self.assertIn("instructions", saved["payload"])
            self.assertIn("input", saved["payload"])
            self.assertIn("schema", saved["payload"])
            self.assertIn("tools", saved["payload"])
            saved_path = Path(prompt.file_path)
            self.assertEqual(saved_path.parent.name, "judgment_group_a")
            self.assertEqual(saved_path.parent.parent.name, "prompts")
            self.assertEqual(saved_path.name, "attempt-1.json")

    def test_mark_prompt_status_updates_request_state(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = PromptCaptureStore(Path(temp_dir))
            prompt = store.capture_prompt(
                run_id="run-1",
                stage_key="judgment_group_a",
                attempt=1,
                model="gpt-5.4",
                payload={"instructions": "x", "input": {}, "schema": {}, "tools": []},
            )

            updated = store.mark_prompt_status(
                "run-1",
                prompt.prompt_id,
                request_status="succeeded",
            )

            self.assertEqual(updated.request_status, "succeeded")
            self.assertIsNone(updated.request_error)
            saved = json.loads(Path(updated.file_path).read_text(encoding="utf-8"))
            self.assertEqual(saved["request_status"], "succeeded")

    def test_get_prompt_raises_corrupted_state_for_invalid_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            run_store = MonitorRunStore(Path(temp_dir) / "runs")
            run = run_store.create_run(date(2026, 4, 11))
            store = PromptCaptureStore(run_store=run_store)
            prompt_path = run_store.resolve_run_dir(run.run_id) / "prompts" / "judgment_group_a" / "attempt-1.json"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text('{"broken":', encoding="utf-8")

            with self.assertRaises(MarketMonitorCorruptedStateError):
                store.get_prompt(run.run_id, "judgment_group_a-attempt-1")

    def test_list_prompts_raises_corrupted_state_for_invalid_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            run_store = MonitorRunStore(Path(temp_dir) / "runs")
            run = run_store.create_run(date(2026, 4, 11))
            store = PromptCaptureStore(run_store=run_store)
            prompt_path = run_store.resolve_run_dir(run.run_id) / "prompts" / "judgment_group_a" / "attempt-1.json"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text('{"broken":', encoding="utf-8")

            with self.assertRaises(MarketMonitorCorruptedStateError):
                store.list_prompts(run.run_id)


if __name__ == "__main__":
    unittest.main()
