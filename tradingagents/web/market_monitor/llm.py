from __future__ import annotations

import json
import os
from threading import BoundedSemaphore
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
        prompt_detail = self.prompt_store.capture_prompt(
            run_id=run_id,
            stage_key=stage_key,
            attempt=attempt,
            model=self.model,
            payload=prompt_payload,
        )
        prompt_id = prompt_detail.prompt_id
        api_key = self._resolve_api_key()
        base_url = self._resolve_base_url()
        if not api_key:
            self.prompt_store.mark_prompt_status(
                run_id,
                prompt_id,
                request_status="rejected",
                request_error=f"{self.provider} API Key 未配置",
            )
            raise MarketMonitorError(f"{self.provider} API Key 未配置")
        if not self._inflight_limiter.acquire(blocking=False):
            self.prompt_store.mark_prompt_status(
                run_id,
                prompt_id,
                request_status="rejected",
                request_error="市场监控 LLM 并发请求过多，请稍后重试",
            )
            raise MarketMonitorError("市场监控 LLM 并发请求过多，请稍后重试")

        self.prompt_store.mark_prompt_status(run_id, prompt_id, request_status="dispatched")

        try:
            client_kwargs: dict[str, Any] = {
                "api_key": api_key,
                "timeout": self.timeout_seconds,
            }
            if base_url:
                client_kwargs["base_url"] = base_url
            client = OpenAI(**client_kwargs)

            response = self._create_response(
                client=client,
                stage_key=stage_key,
                instructions=instructions,
                input_payload=input_payload,
                schema=schema,
                tools=tools or [],
            )
        except MarketMonitorError as exc:
            self.prompt_store.mark_prompt_status(
                run_id,
                prompt_id,
                request_status="failed",
                request_error=str(exc),
            )
            raise
        except Exception as exc:
            self.prompt_store.mark_prompt_status(
                run_id,
                prompt_id,
                request_status="failed",
                request_error=str(exc),
            )
            raise MarketMonitorError(f"{stage_key} 阶段模型请求失败: {exc}") from exc
        finally:
            self._inflight_limiter.release()

        raw_output = getattr(response, "output_text", "") or ""
        payload = extract_json_payload(raw_output)
        if payload is None:
            self.prompt_store.mark_prompt_status(
                run_id,
                prompt_id,
                request_status="failed",
                request_error=f"{stage_key} 阶段模型返回的不是合法 JSON",
            )
            raise MarketMonitorError(f"{stage_key} 阶段模型返回的不是合法 JSON")
        self.prompt_store.mark_prompt_status(run_id, prompt_id, request_status="succeeded")
        return payload

    def _create_response(
        self,
        *,
        client: OpenAI,
        stage_key: str,
        instructions: str,
        input_payload: dict[str, Any],
        schema: dict[str, Any],
        tools: list[dict[str, Any]],
    ) -> Any:
        try:
            return client.responses.create(
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
        except TimeoutError as exc:
            raise MarketMonitorError(f"{stage_key} 阶段模型请求超时") from exc

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
