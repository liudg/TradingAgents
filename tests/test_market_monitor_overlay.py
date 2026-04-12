import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from tradingagents.web.market_monitor.llm import MarketMonitorLlmGateway
from tradingagents.web.market_monitor.prompt_store import PromptCaptureStore


class MarketMonitorOverlayTests(unittest.TestCase):
    def test_prompt_logging_still_happens_without_api_key(self) -> None:
        with TemporaryDirectory() as temp_dir:
            prompt_store = PromptCaptureStore(Path(temp_dir))
            gateway = MarketMonitorLlmGateway(prompt_store)

            with patch.dict(os.environ, {"CODEX_API_KEY": ""}, clear=False):
                payload = gateway.request_json(
                    run_id="run-1",
                    stage_key="judgment_group_a",
                    attempt=1,
                    instructions="你是市场监控裁决器。",
                    input_payload={"observed_facts": ["SPY 站上 MA200"]},
                    schema={"type": "object", "properties": {}},
                )

            self.assertIsNone(payload)
            prompts = prompt_store.list_prompts("run-1")
            self.assertEqual(len(prompts), 1)
            self.assertEqual(prompts[0].stage_key, "judgment_group_a")
            self.assertTrue(
                Path(prompts[0].file_path).as_posix().endswith("run-1/prompts/judgment_group_a/attempt-1.json")
            )

    def test_json_extraction_handles_wrapped_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            gateway = MarketMonitorLlmGateway(PromptCaptureStore(Path(temp_dir)))

            payload = gateway._extract_json_payload("prefix {\"summary\":\"ok\"} suffix")

        self.assertEqual(payload, {"summary": "ok"})

    def test_request_json_configures_client_timeout_and_falls_back_on_timeout(self) -> None:
        with TemporaryDirectory() as temp_dir:
            gateway = MarketMonitorLlmGateway(PromptCaptureStore(Path(temp_dir)))
            mock_client = MagicMock()
            mock_client.responses.create.side_effect = TimeoutError("timed out")

            with patch.dict(os.environ, {"CODEX_API_KEY": "test-key"}, clear=False), patch(
                "tradingagents.web.market_monitor.llm.OpenAI",
                return_value=mock_client,
            ) as mock_openai:
                payload = gateway.request_json(
                    run_id="run-2",
                    stage_key="judgment_group_b",
                    attempt=1,
                    instructions="测试超时处理",
                    input_payload={"observed_facts": ["SPY 站上 MA200"]},
                    schema={"type": "object", "properties": {}},
                )

        self.assertIsNone(payload)
        self.assertEqual(mock_openai.call_args.kwargs["timeout"], gateway.timeout_seconds)

    def test_request_json_uses_hard_timeout_guard_when_client_hangs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            gateway = MarketMonitorLlmGateway(PromptCaptureStore(Path(temp_dir)))
            gateway.timeout_seconds = 0.05
            mock_client = MagicMock()

            def _slow_create(**kwargs):
                time.sleep(0.2)
                return MagicMock(output_text="{\"summary\":\"late\"}")

            mock_client.responses.create.side_effect = _slow_create

            with patch.dict(os.environ, {"CODEX_API_KEY": "test-key"}, clear=False), patch(
                "tradingagents.web.market_monitor.llm.OpenAI",
                return_value=mock_client,
            ):
                started = time.perf_counter()
                payload = gateway.request_json(
                    run_id="run-3",
                    stage_key="execution_decision",
                    attempt=1,
                    instructions="测试硬超时",
                    input_payload={"observed_facts": ["SPY 站上 MA200"]},
                    schema={"type": "object", "properties": {}},
                )
                elapsed = time.perf_counter() - started

        self.assertIsNone(payload)
        self.assertLess(elapsed, 0.15)


if __name__ == "__main__":
    unittest.main()
