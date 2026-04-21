from __future__ import annotations

from pathlib import Path

from tradingagents.web.market_monitor.persistence import MarketMonitorPersistence
from tradingagents.web.market_monitor.schemas import MarketMonitorFactSheet, MarketMonitorRunRequest


class MarketMonitorDebugSupport:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root

    def resolve_fact_sheet(self, request: MarketMonitorRunRequest) -> tuple[MarketMonitorFactSheet | None, str | None]:
        debug_options = request.debug_options
        if debug_options is None or not debug_options.reuse_fact_sheet:
            return None, None
        replay_run_id = debug_options.replay_from_run_id
        if not replay_run_id:
            return None, None
        manifest_path = next(
            (path for path in self.runs_root.rglob("manifest.json") if path.parent.name == replay_run_id),
            None,
        )
        if manifest_path is None:
            raise KeyError(replay_run_id)
        persistence = MarketMonitorPersistence(manifest_path.parent)
        artifact_path = persistence.artifact_path("fact_sheet")
        if not artifact_path.exists():
            return None, replay_run_id
        return persistence.read_fact_sheet_artifact(), replay_run_id
