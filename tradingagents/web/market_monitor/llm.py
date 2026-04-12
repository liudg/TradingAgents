from __future__ import annotations

import json
import os
from queue import Queue
from threading import Thread
from typing import Any

from openai import OpenAI

from tradingagents.default_config import DEFAULT_CONFIG
from .prompt_store import PromptCaptureStore


class MarketMonitorLlmGateway:
    def __init__(self, prompt_store: PromptCaptureStore) -> None:
        self.prompt_store = prompt_store
        self.provider = str(DEFAULT_CONFIG.get("llm_provider", "codex")).strip().lower()
        self.model = str(DEFAULT_CONFIG.get("deep_think_llm", "gpt-5.4"))
        self.timeout_seconds = float(DEFAULT_CONFIG.get("market_monitor_llm_timeout_seconds", 20))
        self.api_key = self._resolve_api_key()
        self.base_url = self._resolve_base_url()

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
        if not self.api_key:
            return None

        client_kwargs: dict[str, Any] = {
            "api_key": self.api_key,
            "timeout": self.timeout_seconds,
        }
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        client = OpenAI(**client_kwargs)

        try:
            response = self._create_response_with_timeout(
                client=client,
                stage_key=stage_key,
                instructions=instructions,
                input_payload=input_payload,
                schema=schema,
                tools=tools or [],
            )
        except Exception:
            return None

        if response is None:
            return None
        raw_output = getattr(response, "output_text", "") or ""
        return self._extract_json_payload(raw_output)

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
        kind, value = result_queue.get_nowait()
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

    def _extract_json_payload(self, content: str) -> dict[str, Any] | None:
        stripped = content.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
