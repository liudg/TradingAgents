from __future__ import annotations

import json
import os
from queue import Empty, Queue
from threading import BoundedSemaphore, Thread
from typing import Any

from openai import OpenAI

from tradingagents.default_config import DEFAULT_CONFIG
from .errors import MarketMonitorError
from .io_utils import extract_json_payload
from .prompt_store import PromptCaptureStore


class MarketMonitorLlmGateway:
    def __init__(self, prompt_store: PromptCaptureStore) -> None:
        self.prompt_store = prompt_store
        self.provider = str(DEFAULT_CONFIG.get("llm_provider", "codex")).strip().lower()
        self.model = str(DEFAULT_CONFIG.get("deep_think_llm", "gpt-5.4"))
        self.timeout_seconds = float(DEFAULT_CONFIG.get("market_monitor_llm_timeout_seconds", 20))
        self.max_inflight_requests = int(DEFAULT_CONFIG.get("market_monitor_llm_max_inflight_requests", 4))
        self._inflight_limiter = BoundedSemaphore(max(1, self.max_inflight_requests))

    def request_json(
        self,
        *,
        run_id: str,
        stage_key: str,
        attempt: int,
        instructions: str,
        input_payload: dict[str, Any],
        schema: dict[str, Any],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        prompt_payload = {
            "instructions": instructions,
            "input": input_payload,
            "schema": schema,
            "tools": tools or [],
        }
        self.prompt_store.capture_prompt(
            run_id=run_id,
            stage_key=stage_key,
            attempt=attempt,
            model=self.model,
            payload=prompt_payload,
        )
        api_key = self._resolve_api_key()
        base_url = self._resolve_base_url()
        if not api_key:
            raise MarketMonitorError(f"{self.provider} API Key 未配置")
        if not self._inflight_limiter.acquire(blocking=False):
            raise MarketMonitorError("市场监控 LLM 并发请求过多，请稍后重试")

        try:
            client_kwargs: dict[str, Any] = {
                "api_key": api_key,
                "timeout": self.timeout_seconds,
            }
            if base_url:
                client_kwargs["base_url"] = base_url
            client = OpenAI(**client_kwargs)

            response = self._create_response_with_timeout(
                client=client,
                stage_key=stage_key,
                instructions=instructions,
                input_payload=input_payload,
                schema=schema,
                tools=tools or [],
            )
        except MarketMonitorError:
            raise
        except Exception as exc:
            raise MarketMonitorError(f"{stage_key} 阶段模型请求失败: {exc}") from exc
        finally:
            self._inflight_limiter.release()

        if response is None:
            raise MarketMonitorError(f"{stage_key} 阶段模型请求超时")
        raw_output = getattr(response, "output_text", "") or ""
        payload = extract_json_payload(raw_output)
        if payload is None:
            raise MarketMonitorError(f"{stage_key} 阶段模型返回的不是合法 JSON")
        return payload

    def _create_response_with_timeout(
        self,
        *,
        client: OpenAI,
        stage_key: str,
        instructions: str,
        input_payload: dict[str, Any],
        schema: dict[str, Any],
        tools: list[dict[str, Any]],
    ) -> Any | None:
        result_queue: Queue[tuple[str, Any]] = Queue(maxsize=1)

        def _invoke() -> None:
            try:
                response = client.responses.create(
                    model=self.model,
                    instructions=instructions,
                    input=json.dumps(input_payload, ensure_ascii=False),
                    reasoning={"effort": "low"},
                    max_output_tokens=2200,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": stage_key,
                            "strict": True,
                            "schema": schema,
                        }
                    },
                    tools=tools,
                )
                result_queue.put(("response", response))
            except Exception as exc:
                result_queue.put(("error", exc))

        worker = Thread(target=_invoke, name=f"market-monitor-{stage_key}", daemon=True)
        worker.start()
        worker.join(timeout=self.timeout_seconds)
        if worker.is_alive():
            return None
        try:
            kind, value = result_queue.get_nowait()
        except Empty:
            return None
        if kind == "error":
            raise value
        return value

    def _resolve_api_key(self) -> str:
        if self.provider == "codex":
            return os.getenv("CODEX_API_KEY", "").strip()
        return os.getenv("OPENAI_API_KEY", "").strip()

    def _resolve_base_url(self) -> str | None:
        if self.provider == "codex":
            return str(DEFAULT_CONFIG.get("backend_url") or "").strip() or None
        return None

    @staticmethod
    def _extract_json_payload(content: str) -> dict[str, Any] | None:
        return extract_json_payload(content)
