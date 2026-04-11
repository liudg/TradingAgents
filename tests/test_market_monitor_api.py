import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

from tradingagents.web.api.app import app, market_monitor_service
from tradingagents.web.market_monitor.schemas import (
    MarketAssessment,
    MarketAssessmentCard,
    MarketAssessmentExecutionCard,
    MarketDataSnapshot,
    MarketMissingDataItem,
)
from tradingagents.web.market_monitor.universe import get_market_monitor_universe


def _make_frame(base: float, days: int = 320) -> pd.DataFrame:
    index = pd.date_range(end=pd.Timestamp("2026-04-10"), periods=days, freq="B")
    close = pd.Series([base + i * 0.3 for i in range(days)], index=index)
    return pd.DataFrame(
        {
            "Open": close - 0.3,
            "High": close + 0.8,
            "Low": close - 0.8,
            "Close": close,
            "Volume": pd.Series([750_000 + i * 50 for i in range(days)], index=index),
        }
    )


def _complete_dataset() -> dict[str, dict[str, pd.DataFrame]]:
    universe = get_market_monitor_universe()
    core = {symbol: _make_frame(100 + idx * 2) for idx, symbol in enumerate(universe["core_index_etfs"])}
    core.update({symbol: _make_frame(80 + idx * 2) for idx, symbol in enumerate(universe["sector_etfs"])})
    core["^VIX"] = _make_frame(20)
    return {"core": core}


def _build_assessment() -> MarketAssessment:
    shared = dict(
        label="偏多",
        summary="本地数据与外部搜索均支持偏多判断。",
        confidence=0.82,
        data_completeness="medium",
        key_evidence=["SPY 站上 MA200", "近期广度改善", "未见新增系统性风险触发器"],
        missing_data_filled_by_search=["未来三日宏观事件窗口", "主要财报日历"],
        action="可以继续参与，但控制事件日前追高。",
    )
    return MarketAssessment(
        long_term_card=MarketAssessmentCard(**shared),
        short_term_card=MarketAssessmentCard(**shared),
        system_risk_card=MarketAssessmentCard(
            **{
                **shared,
                "label": "正常",
                "summary": "系统性风险暂未显著升高。",
                "action": "使用标准风险预算。",
            }
        ),
        event_risk_card=MarketAssessmentCard(
            **{
                **shared,
                "label": "事件密集",
                "summary": "未来三个交易日存在密集宏观与财报事件。",
                "action": "减少事件前追价。",
            }
        ),
        panic_card=MarketAssessmentCard(
            **{
                **shared,
                "label": "未激活",
                "summary": "暂未发现恐慌反转条件。",
                "action": "无需执行恐慌反转策略。",
            }
        ),
        execution_card=MarketAssessmentExecutionCard(
            **shared,
            total_exposure_range="50%-70%",
            new_position_allowed=True,
            chase_breakout_allowed=False,
            dip_buy_allowed=True,
            overnight_allowed=True,
            leverage_allowed=False,
            single_position_cap="10%",
            daily_risk_budget="1.0R",
        ),
    )


class MarketMonitorApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        self.temp_dir = TemporaryDirectory()
        market_monitor_service._dataset_cache.clear()
        market_monitor_service._trace_store = market_monitor_service._trace_store.__class__(
            Path(self.temp_dir.name)
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_snapshot_api_returns_new_assessment_structure(self) -> None:
        dataset = _complete_dataset()
        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            return_value=dataset,
        ), patch.object(
            market_monitor_service._assessment_service,
            "create_assessment",
            return_value=(_build_assessment(), ["example.com"], ["note"], 0.82),
        ), patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            return_value=None,
        ), patch(
            "tradingagents.web.market_monitor.service.save_snapshot_cache",
        ):
            response = self.client.get(
                "/api/market-monitor/snapshot",
                params={"as_of_date": date(2026, 4, 10).isoformat()},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("market_data_snapshot", payload)
        self.assertIn("missing_data", payload)
        self.assertIn("assessment", payload)
        self.assertIn("overall_confidence", payload)
        self.assertEqual(payload["assessment"]["execution_card"]["daily_risk_budget"], "1.0R")
        self.assertEqual(payload["assessment"]["event_risk_card"]["label"], "事件密集")
        self.assertIn("SPY", payload["market_data_snapshot"]["local_market_data"])
        self.assertIn("breadth_above_200dma_pct", payload["market_data_snapshot"]["derived_metrics"])

        trace_id = payload["trace_id"]
        detail_response = self.client.get(f"/api/market-monitor/traces/{trace_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        self.assertEqual(detail_payload["trace_id"], trace_id)
        self.assertEqual(detail_payload["status"], "completed")
        self.assertIn("assessment_summary", detail_payload)
        self.assertEqual(detail_payload["assessment_summary"]["overall_confidence"], 0.82)
        self.assertIn("llm_debug", detail_payload["assessment_summary"])
        self.assertNotIn("log_path", detail_payload)
        self.assertNotIn("snapshot_path", detail_payload)

    def test_data_status_api_reports_missing_data_and_search_mode(self) -> None:
        dataset = _complete_dataset()
        with patch(
            "tradingagents.web.market_monitor.service.build_market_dataset",
            return_value=dataset,
        ), patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            return_value=None,
        ):
            response = self.client.get(
                "/api/market-monitor/data-status",
                params={"as_of_date": date(2026, 4, 10).isoformat()},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["search_enabled"])
        self.assertIn("SPY", payload["available_local_data"])
        self.assertTrue(any(item["key"] == "vix_term_structure" for item in payload["missing_data"]))

    def test_history_api_replays_cached_assessment_summaries(self) -> None:
        snapshot_payload = {
            "timestamp": "2026-04-10T21:00:00",
            "as_of_date": "2026-04-10",
            "trace_id": "trace-1",
            "market_data_snapshot": MarketDataSnapshot(
                local_market_data={"SPY": {"close": 100.0}},
                derived_metrics={"breadth_above_200dma_pct": 75.0},
                llm_reasoning_notes=["test"],
            ).model_dump(mode="json"),
            "missing_data": [
                MarketMissingDataItem(
                    key="vix_term_structure",
                    label="VIX 期限结构",
                    required_for=["long_term_card", "system_risk_card"],
                    status="missing",
                    note="本地未接入",
                ).model_dump(mode="json")
            ],
            "assessment": _build_assessment().model_dump(mode="json"),
            "evidence_sources": ["example.com"],
            "overall_confidence": 0.82,
        }

        with patch(
            "tradingagents.web.market_monitor.service.load_snapshot_cache",
            side_effect=lambda as_of_date: snapshot_payload if as_of_date == date(2026, 4, 10) else None,
        ):
            response = self.client.get(
                "/api/market-monitor/history",
                params={"as_of_date": date(2026, 4, 10).isoformat(), "days": 2},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["points"]), 1)
        self.assertEqual(payload["points"][0]["long_term_label"], "偏多")
        self.assertEqual(payload["points"][0]["overall_confidence"], 0.82)


if __name__ == "__main__":
    unittest.main()
