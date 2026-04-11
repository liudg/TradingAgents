import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from tradingagents.web.market_monitor.llm import MarketMonitorLLMService
from tradingagents.web.market_monitor.schemas import (
    MarketEventRiskFlag,
    MarketIndexEventRisk,
    MarketMonitorModelOverlay,
    MarketMonitorSnapshotResponse,
    MarketMonitorSnapshotRequest,
    MarketMonitorRuleSnapshot,
    MarketSourceCoverage,
    MarketStockEventRisk,
)
from tradingagents.web.market_monitor.service import MarketMonitorService
from tradingagents.web.market_monitor.universe import get_market_monitor_universe


def _make_frame(base: float, days: int = 320) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp("2026-04-10"), periods=days, freq="B")
    close = pd.Series([base + i * 0.35 for i in range(days)], index=index)
    return pd.DataFrame(
        {
            "Open": close - 0.4,
            "High": close + 1.2,
            "Low": close - 1.0,
            "Close": close,
            "Volume": pd.Series([900_000 + i * 80 for i in range(days)], index=index),
        }
    )


def _complete_dataset() -> dict[str, dict[str, pd.DataFrame]]:
    universe = get_market_monitor_universe()
    core = {symbol: _make_frame(110 + idx * 2) for idx, symbol in enumerate(universe["core_index_etfs"])}
    core.update({symbol: _make_frame(85 + idx * 2) for idx, symbol in enumerate(universe["sector_etfs"])})
    core["^VIX"] = _make_frame(19)
    return {"core": core}


class MarketMonitorOverlayTests(unittest.TestCase):
    def test_snapshot_cache_skip_reasons_report_overlay_error(self) -> None:
        service = MarketMonitorService()
        snapshot = MarketMonitorSnapshotResponse(
            timestamp=pd.Timestamp("2026-04-11T21:37:50").to_pydatetime(),
            as_of_date=date(2026, 4, 11),
            rule_snapshot=MarketMonitorRuleSnapshot(
                ready=True,
                base_event_risk_flag=MarketEventRiskFlag(
                    index_level=MarketIndexEventRisk(active=False),
                    stock_level=MarketStockEventRisk(),
                ),
                source_coverage=MarketSourceCoverage(
                    status="partial",
                    data_freshness="live_request_yfinance_daily",
                ),
                missing_inputs=[],
            ),
            model_overlay=MarketMonitorModelOverlay(
                status="error",
                notes=["overlay failed"],
            ),
            final_execution_card=None,
        )

        self.assertEqual(
            service._snapshot_cache_skip_reasons(snapshot),
            ["overlay_error", "missing_final_execution_card"],
        )

    def test_parse_event_risk_coerces_string_action_modifier_into_note(self) -> None:
        service = MarketMonitorLLMService()

        event_risk = service._parse_event_risk(
            {
                "index_level": {
                    "active": True,
                    "type": "FOMC",
                    "days_to_event": 2,
                    "action_modifier": "未来1-3个交易日避免追高，等待波动释放后再评估仓位扩张。",
                },
                "stock_level": {
                    "earnings_stocks": ["NVDA"],
                    "rule": "财报窗口降低隔夜暴露。",
                },
            }
        )

        self.assertIsNotNone(event_risk)
        self.assertTrue(event_risk.index_level.active)
        self.assertEqual(
            event_risk.index_level.action_modifier.note,
            "未来1-3个交易日避免追高，等待波动释放后再评估仓位扩张。",
        )
        self.assertIsNone(event_risk.index_level.action_modifier.new_position_allowed)

    def test_overlay_can_adjust_regime_and_actions_without_changing_base_scores(self) -> None:
        service = MarketMonitorService()
        dataset = _complete_dataset()
        event_override = MarketEventRiskFlag(
            index_level=MarketIndexEventRisk(active=True, type="FOMC", days_to_event=1),
            stock_level=MarketStockEventRisk(
                earnings_stocks=["NVDA"],
                rule="Tighten exposure around event risk.",
            ),
        )
        overlay = MarketMonitorModelOverlay.model_validate(
            {
                "status": "applied",
                "regime_override": "red",
                "execution_adjustments": {
                    "new_position_allowed": False,
                    "daily_risk_budget": "0.10R",
                    "summary": "Macro event risk overrides the base action plan.",
                },
                "event_risk_override": event_override.model_dump(mode="json"),
                "market_narrative": "Macro risk is elevated.",
                "risk_narrative": "Event risk should dominate.",
                "panic_narrative": "No panic score change requested.",
                "evidence_sources": ["https://example.com/fomc"],
                "model_confidence": 0.72,
                "notes": ["overlay test"],
            }
        )

        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            return_value=dataset,
        ), patch.object(
            service._overlay_service,
            "create_overlay",
            return_value=overlay,
        ), patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            return_value=None,
        ), patch(
            "tradingagents.web.market_monitor.service.save_snapshot_cache",
        ):
            response = service.get_snapshot(MarketMonitorSnapshotRequest(as_of_date=date(2026, 4, 10)))

        self.assertTrue(response.rule_snapshot.ready)
        self.assertIsNotNone(response.rule_snapshot.long_term_score)
        self.assertEqual(response.final_execution_card.regime_label, "red")
        self.assertFalse(response.final_execution_card.new_position_allowed)
        self.assertEqual(response.final_execution_card.daily_risk_budget, "0.10R")
        self.assertEqual(response.final_execution_card.event_risk_flag.index_level.type, "FOMC")
        self.assertEqual(
            response.rule_snapshot.long_term_score.score,
            response.rule_snapshot.long_term_score.score,
        )


if __name__ == "__main__":
    unittest.main()
