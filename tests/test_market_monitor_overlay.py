import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from tradingagents.web.market_monitor.errors import MarketMonitorError
from tradingagents.web.market_monitor.prompt_store import PromptCaptureStore
from tradingagents.web.market_monitor.llm import MarketMonitorLlmGateway


class MarketMonitorOverlayTests(unittest.TestCase):
    def test_prompt_logging_still_happens_without_api_key(self) -> None:
        with TemporaryDirectory() as temp_dir:
            prompt_store = PromptCaptureStore(Path(temp_dir))
            gateway = MarketMonitorLlmGateway(prompt_store)

            with patch.dict(os.environ, {"CODEX_API_KEY": ""}, clear=False):
                with self.assertRaisesRegex(MarketMonitorError, "API Key 未配置"):
                    gateway.request_json(
                        run_id="run-1",
                        stage_key="judgment_group_a",
                        attempt=1,
                        instructions="你是市场监控裁决器。",
                        input_payload={"observed_facts": ["SPY 站上 MA200"]},
                        schema={"type": "object", "properties": {}},
                    )

            prompts = prompt_store.list_prompts("run-1")
            self.assertEqual(len(prompts), 1)
            self.assertEqual(prompts[0].stage_key, "judgment_group_a")
            self.assertEqual(prompts[0].request_status, "rejected")
            self.assertIn("API Key 未配置", prompts[0].request_error or "")
            self.assertTrue(
                Path(prompts[0].file_path).as_posix().endswith("run-1/prompts/judgment_group_a/attempt-1.json")
            )

    def test_json_extraction_handles_wrapped_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            gateway = MarketMonitorLlmGateway(PromptCaptureStore(Path(temp_dir)))

            payload = gateway._extract_json_payload("prefix {\"summary\":\"ok\"} suffix")

        self.assertEqual(payload, {"summary": "ok"})

    def test_request_json_configures_client_timeout_and_raises_on_client_timeout(self) -> None:
        with TemporaryDirectory() as temp_dir:
            gateway = MarketMonitorLlmGateway(PromptCaptureStore(Path(temp_dir)))
            mock_client = MagicMock()
            mock_client.responses.create.side_effect = TimeoutError("timed out")

            with patch.dict(os.environ, {"CODEX_API_KEY": "test-key"}, clear=False), patch(
                "tradingagents.web.market_monitor.llm.OpenAI",
                return_value=mock_client,
            ) as mock_openai:
                with self.assertRaisesRegex(MarketMonitorError, "模型请求超时"):
                    gateway.request_json(
                        run_id="run-2",
                        stage_key="judgment_group_b",
                        attempt=1,
                        instructions="测试超时处理",
                        input_payload={"observed_facts": ["SPY 站上 MA200"]},
                        schema={"type": "object", "properties": {}},
                    )

            self.assertEqual(mock_openai.call_args.kwargs["timeout"], gateway.timeout_seconds)
            prompts = gateway.prompt_store.list_prompts("run-2")
            self.assertEqual(prompts[0].request_status, "failed")
            self.assertIn("模型请求超时", prompts[0].request_error or "")

    def test_request_json_marks_timeout_without_background_thread(self) -> None:
        with TemporaryDirectory() as temp_dir:
            gateway = MarketMonitorLlmGateway(PromptCaptureStore(Path(temp_dir)))
            mock_client = MagicMock()
            mock_client.responses.create.side_effect = TimeoutError("timed out")

            with patch.dict(os.environ, {"CODEX_API_KEY": "test-key"}, clear=False), patch(
                "tradingagents.web.market_monitor.llm.OpenAI",
                return_value=mock_client,
            ):
                with self.assertRaisesRegex(MarketMonitorError, "模型请求超时"):
                    gateway.request_json(
                        run_id="run-3",
                        stage_key="execution_decision",
                        attempt=1,
                        instructions="测试超时",
                        input_payload={"observed_facts": ["SPY 站上 MA200"]},
                        schema={"type": "object", "properties": {}},
                    )

            prompts = gateway.prompt_store.list_prompts("run-3")
            self.assertEqual(prompts[0].request_status, "failed")
            self.assertIn("模型请求超时", prompts[0].request_error or "")
            self.assertEqual(mock_client.responses.create.call_count, 1)

    def test_request_json_rejects_when_inflight_limit_is_exhausted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            gateway = MarketMonitorLlmGateway(PromptCaptureStore(Path(temp_dir)))
            gateway.max_inflight_requests = 1
            gateway._inflight_limiter = gateway._inflight_limiter.__class__(1)
            self.assertTrue(gateway._inflight_limiter.acquire(blocking=False))

            with patch.dict(os.environ, {"CODEX_API_KEY": "test-key"}, clear=False):
                with self.assertRaisesRegex(MarketMonitorError, "并发请求过多"):
                    gateway.request_json(
                        run_id="run-4",
                        stage_key="judgment_group_a",
                        attempt=1,
                        instructions="测试并发限流",
                        input_payload={"observed_facts": ["SPY 站上 MA200"]},
                        schema={"type": "object", "properties": {}},
                    )

            prompts = gateway.prompt_store.list_prompts("run-4")
            self.assertEqual(prompts[0].request_status, "rejected")
            self.assertIn("并发请求过多", prompts[0].request_error or "")
            gateway._inflight_limiter.release()

    def test_request_json_marks_prompt_succeeded_on_valid_response(self) -> None:
        with TemporaryDirectory() as temp_dir:
            gateway = MarketMonitorLlmGateway(PromptCaptureStore(Path(temp_dir)))
            mock_client = MagicMock()
            mock_client.responses.create.return_value = MagicMock(output_text='{"summary":"ok"}')

            with patch.dict(os.environ, {"CODEX_API_KEY": "test-key"}, clear=False), patch(
                "tradingagents.web.market_monitor.llm.OpenAI",
                return_value=mock_client,
            ):
                payload = gateway.request_json(
                    run_id="run-5",
                    stage_key="execution_decision",
                    attempt=1,
                    instructions="测试成功路径",
                    input_payload={"observed_facts": ["SPY 站上 MA200"]},
                    schema={"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"], "additionalProperties": False},
                )

            self.assertEqual(payload, {"summary": "ok"})
            prompts = gateway.prompt_store.list_prompts("run-5")
            self.assertEqual(prompts[0].request_status, "succeeded")
            self.assertIsNone(prompts[0].request_error)


if __name__ == "__main__":
    unittest.main()
