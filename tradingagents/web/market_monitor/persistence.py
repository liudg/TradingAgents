from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tradingagents.web.market_monitor.io_utils import write_json_atomic
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorDataStatusResponse,
    MarketMonitorDebugCardResponse,
    MarketMonitorFactSheet,
    MarketMonitorHistoryResponse,
    MarketMonitorPromptTrace,
    MarketMonitorRunManifest,
    MarketMonitorSnapshotResponse,
    MarketMonitorStageResult,
)


class MarketMonitorPersistence:
    def __init__(self, results_dir: Path) -> None:
        self.results_dir = results_dir
        self.stages_dir = results_dir / "stages"
        self.artifacts_dir = results_dir / "artifacts"
        self.prompt_traces_dir = results_dir / "prompt_traces"

    def ensure_layout(self) -> None:
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.stages_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.prompt_traces_dir.mkdir(parents=True, exist_ok=True)

    def manifest_path(self) -> Path:
        return self.results_dir / "manifest.json"

    def write_manifest(self, manifest: MarketMonitorRunManifest) -> Path:
        self.ensure_layout()
        path = self.manifest_path()
        write_json_atomic(path, manifest.model_dump(mode="json"))
        return path

    def read_manifest(self) -> MarketMonitorRunManifest:
        payload = json.loads(self.manifest_path().read_text(encoding="utf-8"))
        return MarketMonitorRunManifest.model_validate(payload)

    def stage_path(self, stage_name: str) -> Path:
        return self.stages_dir / f"{stage_name}.json"

    def write_stage_result(self, stage_result: MarketMonitorStageResult, payload: dict[str, Any] | None = None) -> Path:
        self.ensure_layout()
        path = self.stage_path(stage_result.stage_name)
        content = {
            "stage_result": stage_result.model_dump(mode="json"),
            "payload": payload or {},
        }
        write_json_atomic(path, content)
        return path

    def read_stage_payload(self, stage_name: str) -> dict[str, Any]:
        path = self.stage_path(stage_name)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload

    def read_artifact_payload(self, artifact_name: str) -> dict[str, Any]:
        path = self.artifact_path(artifact_name)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload

    def artifact_path(self, artifact_name: str) -> Path:
        return self.artifacts_dir / f"{artifact_name}.json"

    def write_artifact_payload(self, artifact_name: str, payload: dict[str, Any]) -> Path:
        self.ensure_layout()
        path = self.artifact_path(artifact_name)
        write_json_atomic(path, payload)
        return path

    def write_snapshot_artifact(self, snapshot: MarketMonitorSnapshotResponse) -> Path:
        self.ensure_layout()
        path = self.artifact_path("snapshot")
        write_json_atomic(path, snapshot.model_dump(mode="json"))
        return path

    def write_history_artifact(self, history: MarketMonitorHistoryResponse) -> Path:
        self.ensure_layout()
        path = self.artifact_path("history")
        write_json_atomic(path, history.model_dump(mode="json"))
        return path

    def write_data_status_artifact(self, data_status: MarketMonitorDataStatusResponse) -> Path:
        self.ensure_layout()
        path = self.artifact_path("data_status")
        write_json_atomic(path, data_status.model_dump(mode="json"))
        return path

    def write_fact_sheet_artifact(self, fact_sheet: MarketMonitorFactSheet) -> Path:
        self.ensure_layout()
        path = self.artifact_path("fact_sheet")
        write_json_atomic(path, fact_sheet.model_dump(mode="json"))
        return path

    def write_debug_card_artifact(self, debug_card: MarketMonitorDebugCardResponse) -> Path:
        self.ensure_layout()
        path = self.artifact_path("debug_card")
        write_json_atomic(path, debug_card.model_dump(mode="json"))
        return path

    def read_snapshot_artifact(self) -> MarketMonitorSnapshotResponse:
        payload = json.loads(self.artifact_path("snapshot").read_text(encoding="utf-8"))
        return MarketMonitorSnapshotResponse.model_validate(payload)

    def read_history_artifact(self) -> MarketMonitorHistoryResponse:
        payload = json.loads(self.artifact_path("history").read_text(encoding="utf-8"))
        return MarketMonitorHistoryResponse.model_validate(payload)

    def read_data_status_artifact(self) -> MarketMonitorDataStatusResponse:
        payload = json.loads(self.artifact_path("data_status").read_text(encoding="utf-8"))
        return MarketMonitorDataStatusResponse.model_validate(payload)

    def read_fact_sheet_artifact(self) -> MarketMonitorFactSheet:
        payload = json.loads(self.artifact_path("fact_sheet").read_text(encoding="utf-8"))
        return MarketMonitorFactSheet.model_validate(payload)

    def read_debug_card_artifact(self) -> MarketMonitorDebugCardResponse:
        payload = json.loads(self.artifact_path("debug_card").read_text(encoding="utf-8"))
        return MarketMonitorDebugCardResponse.model_validate(payload)

    def prompt_trace_path(self, trace_name: str) -> Path:
        return self.prompt_traces_dir / f"{trace_name}.json"

    def write_prompt_trace(self, trace_name: str, trace: MarketMonitorPromptTrace) -> Path:
        self.ensure_layout()
        path = self.prompt_trace_path(trace_name)
        write_json_atomic(path, trace.model_dump(mode="json"))
        return path

    def read_prompt_trace(self, trace_name: str) -> MarketMonitorPromptTrace:
        payload = json.loads(self.prompt_trace_path(trace_name).read_text(encoding="utf-8"))
        return MarketMonitorPromptTrace.model_validate(payload)

    def list_prompt_traces(self) -> list[MarketMonitorPromptTrace]:
        if not self.prompt_traces_dir.exists():
            return []
        traces: list[MarketMonitorPromptTrace] = []
        for path in sorted(self.prompt_traces_dir.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            traces.append(MarketMonitorPromptTrace.model_validate(payload))
        return traces
