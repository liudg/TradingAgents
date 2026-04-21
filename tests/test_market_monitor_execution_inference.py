import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from tradingagents.web.market_monitor.inference.execution import MarketMonitorExecutionInferenceService
from tradingagents.web.market_monitor.prompts.execution import build_execution_prompt
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorActionModifier,
    MarketMonitorEventRiskFlag,
    MarketMonitorFactSheet,
    MarketMonitorIndexEventRisk,
    MarketMonitorLayerMetric,
    MarketMonitorScoreCard,
    MarketMonitorSignalConfirmation,
    MarketMonitorSourceCoverage,
    MarketMonitorStockEventRisk,
    MarketMonitorStyleAssetLayer,
    MarketMonitorStyleEffectiveness,
    MarketMonitorStyleTacticLayer,
    MarketMonitorSystemRiskCard,
    MarketMonitorExecutionCard,
)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLlm:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, messages):
        return _FakeResponse(self._content)


class MarketMonitorExecutionInferenceTests(unittest.TestCase):
    def _build_inputs(self):
        now = datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)
        fact_sheet = MarketMonitorFactSheet(
            as_of_date=date(2026, 4, 11),
            generated_at=now,
            local_facts={"symbols": {"SPY": {"latest_close": 523.1}}},
            derived_metrics={"breadth_above_200dma_pct": 63.0},
            open_gaps=["缺少交易所级 breadth 原始数据"],
            source_coverage=MarketMonitorSourceCoverage(
                completeness="medium",
                available_sources=["ETF/指数日线"],
                missing_sources=["交易所级 breadth"],
                degraded=True,
            ),
            notes=["已按代理池与降级规则输出结果。"],
        )
        long_term = MarketMonitorScoreCard(
            score=68.5,
            zone="进攻区",
            delta_1d=2.1,
            delta_5d=8.2,
            slope_state="缓慢改善",
            summary="长线环境偏多。",
            action="建议维持趋势仓。",
        )
        short_term = MarketMonitorScoreCard(
            score=61.3,
            zone="可做区",
            delta_1d=1.1,
            delta_5d=4.6,
            slope_state="缓慢改善",
            summary="短线环境允许参与。",
            action="优先低吸。",
        )
        system_risk = MarketMonitorSystemRiskCard(
            score=34.6,
            zone="正常区",
            delta_1d=-1.2,
            delta_5d=-3.5,
            slope_state="缓慢恶化",
            summary="系统性风险可控。",
            action="维持常规风控。",
            liquidity_stress_score=31.2,
            risk_appetite_score=38.0,
        )
        style = MarketMonitorStyleEffectiveness(
            tactic_layer=MarketMonitorStyleTacticLayer(
                trend_breakout=MarketMonitorLayerMetric(score=52, delta_5d=0.8, valid=False),
                dip_buy=MarketMonitorLayerMetric(score=66, delta_5d=3.4, valid=True),
                oversold_bounce=MarketMonitorLayerMetric(score=58, delta_5d=2.1, valid=True),
                top_tactic="回调低吸",
                avoid_tactic="趋势突破",
            ),
            asset_layer=MarketMonitorStyleAssetLayer(
                large_cap_tech=MarketMonitorLayerMetric(score=61, delta_5d=3.2, preferred=True),
                small_cap_momentum=MarketMonitorLayerMetric(score=44, delta_5d=-1.2, preferred=False),
                defensive=MarketMonitorLayerMetric(score=70, delta_5d=2.8, preferred=True),
                energy_cyclical=MarketMonitorLayerMetric(score=64, delta_5d=1.8, preferred=True),
                financials=MarketMonitorLayerMetric(score=49, delta_5d=0.4, preferred=False),
                preferred_assets=["防御板块", "能源/周期"],
                avoid_assets=["小盘高弹性"],
            ),
        )
        event_risk = MarketMonitorEventRiskFlag(
            index_level=MarketMonitorIndexEventRisk(
                active=True,
                type="宏观窗口",
                days_to_event=1,
                action_modifier=MarketMonitorActionModifier(note="减少追高。"),
            ),
            stock_level=MarketMonitorStockEventRisk(
                earnings_stocks=["NVDA"],
                rule="财报股单票上限减半。",
            ),
        )
        return fact_sheet, long_term, short_term, system_risk, style, event_risk

    def test_execution_inference_parses_json(self) -> None:
        content = """
        {
          "regime_label": "黄绿灯-Swing",
          "conflict_mode": "长线中性+短线活跃+风险低",
          "total_exposure_range": "50%-70%",
          "new_position_allowed": true,
          "chase_breakout_allowed": true,
          "dip_buy_allowed": true,
          "overnight_allowed": true,
          "leverage_allowed": false,
          "single_position_cap": "12%",
          "daily_risk_budget": "1.0R",
          "tactic_preference": "回调低吸 > 趋势突破",
          "preferred_assets": ["防御板块", "能源/周期"],
          "avoid_assets": ["小盘高弹性"],
          "signal_confirmation": {
            "current_regime_days": 1,
            "downgrade_unlock_in_days": 2,
            "note": "当前 regime 为新近状态，继续观察 2 个交易日。"
          },
          "event_risk_flag": {
            "index_level": {
              "active": true,
              "type": "宏观窗口",
              "days_to_event": 1,
              "action_modifier": {"note": "减少追高。"}
            },
            "stock_level": {
              "earnings_stocks": ["NVDA"],
              "rule": "财报股单票上限减半。"
            }
          },
          "summary": "当前处于黄绿灯-Swing，总仓建议 50%-70%。",
          "reasoning_summary": "长线中性、短线活跃且系统风险可控。",
          "key_drivers": ["长线进攻区", "系统风险正常区"],
          "risks": ["breadth 仍为代理"],
          "confidence": "medium"
        }
        """
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(content)})(),
        ):
            service = MarketMonitorExecutionInferenceService()
            fact_sheet, long_term, short_term, system_risk, style, event_risk = self._build_inputs()
            result = service.infer_execution(
                fact_sheet=fact_sheet,
                long_term=long_term,
                short_term=short_term,
                system_risk=system_risk,
                style=style,
                event_risk=event_risk,
                fallback=lambda: MarketMonitorExecutionCard(
                    regime_label="黄灯",
                    conflict_mode="fallback",
                    total_exposure_range="40%-60%",
                    new_position_allowed=True,
                    chase_breakout_allowed=False,
                    dip_buy_allowed=True,
                    overnight_allowed=True,
                    leverage_allowed=False,
                    single_position_cap="10%",
                    daily_risk_budget="0.75R",
                    tactic_preference="回调低吸 > 趋势突破",
                    preferred_assets=["防御板块"],
                    avoid_assets=[],
                    signal_confirmation=MarketMonitorSignalConfirmation(
                        current_regime_days=1,
                        downgrade_unlock_in_days=2,
                        note="fallback",
                    ),
                    event_risk_flag=event_risk,
                    summary="fallback",
                ),
            )

        self.assertEqual(result.payload.regime_label, "黄绿灯-Swing")
        self.assertFalse(result.used_fallback)
        self.assertEqual(result.trace.stage, "execution_aggregation")

    def test_execution_prompt_includes_framework_constraints(self) -> None:
        fact_sheet, long_term, short_term, system_risk, style, event_risk = self._build_inputs()
        system_prompt, user_prompt, input_summary = build_execution_prompt(
            fact_sheet,
            long_term,
            short_term,
            system_risk,
            style,
            event_risk,
        )

        self.assertIn("decision_framework", user_prompt)
        self.assertIn("conflict_matrix", user_prompt)
        self.assertIn("event_risk_rules", user_prompt)
        self.assertIn("signal_confirmation_rules", user_prompt)
        self.assertIn("current_regime_days", user_prompt)
        self.assertIn("以规则为准", system_prompt)
        self.assertEqual(input_summary, "execution aggregation facts")

    def test_execution_inference_falls_back_when_json_invalid(self) -> None:
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm("not json")})(),
        ):
            service = MarketMonitorExecutionInferenceService()
            fact_sheet, long_term, short_term, system_risk, style, event_risk = self._build_inputs()
            result = service.infer_execution(
                fact_sheet=fact_sheet,
                long_term=long_term,
                short_term=short_term,
                system_risk=system_risk,
                style=style,
                event_risk=event_risk,
                fallback=lambda: MarketMonitorExecutionCard(
                    regime_label="黄绿灯-Swing",
                    conflict_mode="长线中性+短线活跃+风险低",
                    total_exposure_range="50%-70%",
                    new_position_allowed=True,
                    chase_breakout_allowed=True,
                    dip_buy_allowed=True,
                    overnight_allowed=True,
                    leverage_allowed=False,
                    single_position_cap="10%",
                    daily_risk_budget="1.0R",
                    tactic_preference="回调低吸 > 趋势突破",
                    preferred_assets=["防御板块", "能源/周期"],
                    avoid_assets=["小盘高弹性"],
                    signal_confirmation=MarketMonitorSignalConfirmation(
                        current_regime_days=1,
                        downgrade_unlock_in_days=2,
                        note="fallback",
                    ),
                    event_risk_flag=event_risk,
                    summary="fallback",
                ),
            )

        self.assertTrue(result.used_fallback)
        self.assertEqual(result.payload.regime_label, "黄绿灯-Swing")
        self.assertFalse(result.trace.parsed_ok)


if __name__ == "__main__":
    unittest.main()
