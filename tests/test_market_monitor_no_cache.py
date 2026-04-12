import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from tradingagents.web.market_monitor.prompt_store import PromptCaptureStore


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
            self.assertIn("instructions", saved["payload"])
            self.assertIn("input", saved["payload"])
            self.assertIn("schema", saved["payload"])
            self.assertIn("tools", saved["payload"])
            saved_path = Path(prompt.file_path)
            self.assertEqual(saved_path.parent.name, "judgment_group_a")
            self.assertEqual(saved_path.parent.parent.name, "prompts")
            self.assertEqual(saved_path.name, "attempt-1.json")


if __name__ == "__main__":
    unittest.main()
