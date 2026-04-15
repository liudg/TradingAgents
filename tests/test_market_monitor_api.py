import unittest
from datetime import date, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from tradingagents.web.api.app import app
from tradingagents.web.market_monitor.schemas import (
    ExecutionDecisionPack,
    MarketMonitorPromptDetail,
    MarketMonitorPromptSummary,
    MarketMonitorRunCreateRequest,
    MarketMonitorRunCreateResponse,
    MarketMonitorRunDetail,
    MarketMonitorRunEvidenceResponse,
    MarketMonitorRunLogEntry,
    MarketMonitorRunResultSummary,
    MarketMonitorRunStageDetail,
    MarketMonitorRunStagesResponse,
)


class MarketMonitorRunApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_run_api_exposes_pipeline_resources(self) -> None:
        run_id = "run-123"
        created_at = datetime(2026, 4, 12, 9, 30, 0)
        run_detail = MarketMonitorRunDetail(
            run_id=run_id,
            as_of_date=date(2026, 4, 11),
            status="completed",
            current_stage="completed",
            created_at=created_at,
            started_at=created_at,
            finished_at=created_at,
            error_message=None,
            result=MarketMonitorRunResultSummary(
                long_term_label="偏多",
                system_risk_label="可控",
                short_term_label="可做",
                event_risk_label="事件密集",
                panic_label="未激活",
                execution_summary="维持偏多但控制事件前追价。",
                execution=ExecutionDecisionPack(
                    summary="维持偏多但控制事件前追价。",
                    confidence=0.78,
                    decision_basis=["趋势偏多", "未来三日事件密集"],
                    tradeoffs=["允许持仓，但不鼓励重仓追高"],
                    risk_flags=["财报密集窗口"],
                    actions=[
                        "总仓位控制在 50%-70%",
                        "优先低吸，减少事件日前追高",
                    ],
                ),
            ),
        )
        stages = MarketMonitorRunStagesResponse(
            run_id=run_id,
            stages=[
                MarketMonitorRunStageDetail(
                    stage_key="input_bundle",
                    label="本地输入摘要",
                    status="completed",
                    started_at=created_at,
                    finished_at=created_at,
                    summary={"available_local_data": ["SPY", "QQQ", "^VIX"]},
                ),
                MarketMonitorRunStageDetail(
                    stage_key="fact_sheet",
                    label="事实整编",
                    status="completed",
                    started_at=created_at,
                    finished_at=created_at,
                    summary={"observed_fact_count": 5, "filled_fact_count": 2},
                ),
            ],
        )
        evidence = MarketMonitorRunEvidenceResponse(
            run_id=run_id,
            evidence_index={
                "fact_spy_trend": [
                    {
                        "slot_key": "macro_calendar",
                        "source": "fed.gov",
                        "published_at": "2026-04-11T08:00:00",
                        "title": "FOMC schedule",
                    }
                ]
            },
            search_slots={
                "macro_calendar": [
                    {
                        "slot_key": "macro_calendar",
                        "title": "FOMC schedule",
                        "summary": "",
                        "source": "fed.gov",
                        "published_at": "2026-04-11T08:00:00",
                    }
                ]
            },
            open_gaps=["breadth 原始交易所数据未补齐"],
        )
        logs = [
            MarketMonitorRunLogEntry(
                line_no=1,
                timestamp=created_at,
                level="FactSheet",
                content="事实整编完成",
            )
        ]
        prompts = [
            MarketMonitorPromptSummary(
                prompt_id="judgment_group_a-attempt-1",
                run_id=run_id,
                stage_key="judgment_group_a",
                attempt=1,
                created_at=created_at,
                model="gpt-5.4",
            )
        ]
        prompt_detail = MarketMonitorPromptDetail(
            prompt_id="judgment_group_a-attempt-1",
            run_id=run_id,
            stage_key="judgment_group_a",
            attempt=1,
            created_at=created_at,
            model="gpt-5.4",
            payload={
                "instructions": "你是市场监控裁决器。",
                "input": {"observed_facts": ["SPY 站上 200 日均线"]},
                "tools": [{"type": "web_search"}],
                "schema": {"type": "object"},
            },
        )

        with patch(
            "tradingagents.web.api.app.market_monitor_service.create_run",
            return_value=MarketMonitorRunCreateResponse(run_id=run_id, status="running"),
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_run",
            return_value=run_detail,
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_run_stages",
            return_value=stages,
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_run_evidence",
            return_value=evidence,
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.list_run_logs",
            return_value=logs,
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.list_run_prompts",
            return_value=prompts,
        ), patch(
            "tradingagents.web.api.app.market_monitor_service.get_prompt_detail",
            return_value=prompt_detail,
        ):
            create_response = self.client.post(
                "/api/market-monitor/runs",
                json=MarketMonitorRunCreateRequest(as_of_date=date(2026, 4, 11)).model_dump(mode="json"),
            )
            detail_response = self.client.get(f"/api/market-monitor/runs/{run_id}")
            stages_response = self.client.get(f"/api/market-monitor/runs/{run_id}/stages")
            evidence_response = self.client.get(f"/api/market-monitor/runs/{run_id}/evidence")
            logs_response = self.client.get(f"/api/market-monitor/runs/{run_id}/logs")
            prompts_response = self.client.get(f"/api/market-monitor/runs/{run_id}/prompts")
            prompt_detail_response = self.client.get(
                f"/api/market-monitor/runs/{run_id}/prompts/judgment_group_a-attempt-1"
            )

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json()["run_id"], run_id)
        self.assertEqual(create_response.json()["status"], "running")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["result"]["long_term_label"], "偏多")
        self.assertEqual(stages_response.status_code, 200)
        self.assertEqual(stages_response.json()["stages"][1]["stage_key"], "fact_sheet")
        self.assertEqual(evidence_response.status_code, 200)
        self.assertIn("fact_spy_trend", evidence_response.json()["evidence_index"])
        self.assertEqual(logs_response.status_code, 200)
        self.assertEqual(logs_response.json()[0]["level"], "FactSheet")
        self.assertEqual(prompts_response.status_code, 200)
        self.assertEqual(prompts_response.json()[0]["stage_key"], "judgment_group_a")
        self.assertEqual(prompt_detail_response.status_code, 200)
        self.assertIn("instructions", prompt_detail_response.json()["payload"])

    def test_prompts_api_returns_404_for_missing_run(self) -> None:
        response = self.client.get("/api/market-monitor/runs/missing-run/prompts")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "未找到市场监控提示词记录")

    def test_logs_api_returns_404_for_missing_run(self) -> None:
        response = self.client.get("/api/market-monitor/runs/missing-run/logs")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "未找到市场监控日志")

    def test_prompt_detail_api_returns_404_for_invalid_prompt_id(self) -> None:
        run_id = "run-123"
        created_at = datetime(2026, 4, 12, 9, 30, 0)
        run_detail = MarketMonitorRunDetail(
            run_id=run_id,
            as_of_date=date(2026, 4, 11),
            status="completed",
            current_stage="completed",
            created_at=created_at,
            started_at=created_at,
            finished_at=created_at,
            error_message=None,
            result=None,
        )

        with patch(
            "tradingagents.web.api.app.market_monitor_service.get_run",
            return_value=run_detail,
        ):
            response = self.client.get(f"/api/market-monitor/runs/{run_id}/prompts/bad-id")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "未找到提示词详情")


if __name__ == "__main__":
    unittest.main()
