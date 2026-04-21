import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

from tradingagents.web.market_monitor.inference.cards import MarketMonitorCardInferenceService
from tradingagents.web.market_monitor.schemas import (
    MarketMonitorEvidenceRef,
    MarketMonitorEventRiskFlag,
    MarketMonitorFactSheet,
    MarketMonitorLayerMetric,
    MarketMonitorPanicCard,
    MarketMonitorScoreCard,
    MarketMonitorSourceCoverage,
    MarketMonitorStyleAssetLayer,
    MarketMonitorStyleEffectiveness,
    MarketMonitorStyleTacticLayer,
    MarketMonitorSystemRiskCard,
)


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLlm:
    def __init__(self, content: str) -> None:
        self._content = content

    def invoke(self, messages):
        return _FakeResponse(self._content)


class MarketMonitorInferenceTests(unittest.TestCase):
    def _build_fact_sheet(self) -> MarketMonitorFactSheet:
        now = datetime(2026, 4, 12, 9, 30, 0, tzinfo=timezone.utc)
        return MarketMonitorFactSheet(
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
            evidence_refs=[
                MarketMonitorEvidenceRef(
                    source_type="local_market_data",
                    source_label="SPY 日线",
                    snippet="SPY close 523.1",
                    confidence="high",
                )
            ],
            notes=["已按代理池与降级规则输出结果。"],
        )

    def test_long_term_inference_parses_strict_json(self) -> None:
        content = """
        {
          "score": 72.5,
          "zone": "进攻区",
          "delta_1d": 1.2,
          "delta_5d": 5.8,
          "slope_state": "缓慢改善",
          "summary": "长线环境改善。",
          "action": "维持趋势仓。",
          "recommended_exposure": "60%-80%",
          "reasoning_summary": "趋势与广度同时改善。",
          "key_drivers": ["SPY 位于高位", "广度回升"],
          "risks": ["breadth 仍为代理"],
          "confidence": "medium"
        }
        """
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(content)})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_long_term(
                self._build_fact_sheet(),
                fallback=lambda: MarketMonitorScoreCard(
                    score=50,
                    zone="观察区",
                    delta_1d=0,
                    delta_5d=0,
                    slope_state="钝化震荡",
                    summary="fallback",
                    action="fallback",
                ),
            )

        self.assertEqual(result.payload.zone, "进攻区")
        self.assertFalse(result.used_fallback)
        self.assertTrue(result.trace.parsed_ok)
        self.assertEqual(result.trace.card_type, "long_term")

    def test_system_risk_inference_falls_back_when_json_invalid(self) -> None:
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm("not json")})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_system_risk(
                self._build_fact_sheet(),
                fallback=lambda: MarketMonitorSystemRiskCard(
                    score=34.6,
                    zone="正常区",
                    delta_1d=-1.2,
                    delta_5d=-3.5,
                    slope_state="缓慢恶化",
                    summary="系统性风险可控。",
                    action="维持常规风控。",
                    liquidity_stress_score=31.2,
                    risk_appetite_score=38.0,
                ),
            )

        self.assertTrue(result.used_fallback)
        self.assertFalse(result.trace.parsed_ok)
        self.assertEqual(result.payload.zone, "正常区")
        self.assertIsNotNone(result.trace.error)

    def test_event_risk_inference_parses_nested_json(self) -> None:
        content = """
        {
          "index_level": {
            "active": true,
            "type": "宏观窗口",
            "days_to_event": 1,
            "action_modifier": {
              "new_position_allowed": true,
              "overnight_allowed": true,
              "single_position_cap_multiplier": 0.8,
              "note": "减少追高。"
            }
          },
          "stock_level": {
            "earnings_stocks": ["NVDA"],
            "rule": "财报股单票上限减半。"
          },
          "reasoning_summary": "未来一日存在宏观扰动和财报事件。",
          "key_drivers": ["宏观窗口", "重点财报股"],
          "risks": ["缺少真实事件日历"],
          "confidence": "low"
        }
        """
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(content)})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_event_risk(
                self._build_fact_sheet(),
                fallback=lambda: MarketMonitorEventRiskFlag(),
            )

        self.assertTrue(result.payload.index_level.active)
        self.assertEqual(result.payload.stock_level.earnings_stocks, ["NVDA"])
        self.assertEqual(result.payload.confidence, "low")

    def test_short_term_inference_parses_json(self) -> None:
        content = """
        {
          "score": 63.4,
          "zone": "可做区",
          "delta_1d": 1.0,
          "delta_5d": 4.1,
          "slope_state": "缓慢改善",
          "summary": "短线环境允许参与。",
          "action": "优先低吸。",
          "reasoning_summary": "行业动量扩散改善，波动尚可承受。",
          "key_drivers": ["行业 ETF 扩散修复", "SPY 波动可控"],
          "risks": ["breadth 仍为代理"],
          "confidence": "medium"
        }
        """
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(content)})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_short_term(
                self._build_fact_sheet(),
                fallback=lambda: MarketMonitorScoreCard(
                    score=50,
                    zone="观察区",
                    delta_1d=0,
                    delta_5d=0,
                    slope_state="钝化震荡",
                    summary="fallback",
                    action="fallback",
                ),
            )

        self.assertFalse(result.used_fallback)
        self.assertEqual(result.payload.zone, "可做区")
        self.assertEqual(result.trace.card_type, "short_term")

    def test_style_inference_parses_nested_json(self) -> None:
        content = """
        {
          "tactic_layer": {
            "trend_breakout": {"score": 52, "delta_5d": 0.8, "valid": false},
            "dip_buy": {"score": 66, "delta_5d": 3.4, "valid": true},
            "oversold_bounce": {"score": 58, "delta_5d": 2.1, "valid": true},
            "top_tactic": "回调低吸",
            "avoid_tactic": "趋势突破"
          },
          "asset_layer": {
            "large_cap_tech": {"score": 61, "delta_5d": 3.2, "preferred": true},
            "small_cap_momentum": {"score": 44, "delta_5d": -1.2, "preferred": false},
            "defensive": {"score": 70, "delta_5d": 2.8, "preferred": true},
            "energy_cyclical": {"score": 64, "delta_5d": 1.8, "preferred": true},
            "financials": {"score": 49, "delta_5d": 0.4, "preferred": false},
            "preferred_assets": ["防御板块", "能源/周期"],
            "avoid_assets": ["小盘高弹性"]
          },
          "reasoning_summary": "回调低吸与防御/周期资产更占优。",
          "key_drivers": ["大盘科技强于小盘", "防御资产相对占优"],
          "risks": ["股票级 RS 缺失"],
          "confidence": "medium"
        }
        """
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm(content)})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_style(
                self._build_fact_sheet(),
                fallback=lambda: MarketMonitorStyleEffectiveness(
                    tactic_layer=MarketMonitorStyleTacticLayer(
                        trend_breakout=MarketMonitorLayerMetric(score=50, delta_5d=0.0, valid=False),
                        dip_buy=MarketMonitorLayerMetric(score=50, delta_5d=0.0, valid=False),
                        oversold_bounce=MarketMonitorLayerMetric(score=50, delta_5d=0.0, valid=False),
                        top_tactic="回调低吸",
                        avoid_tactic="趋势突破",
                    ),
                    asset_layer=MarketMonitorStyleAssetLayer(
                        large_cap_tech=MarketMonitorLayerMetric(score=50, delta_5d=0.0, preferred=False),
                        small_cap_momentum=MarketMonitorLayerMetric(score=50, delta_5d=0.0, preferred=False),
                        defensive=MarketMonitorLayerMetric(score=50, delta_5d=0.0, preferred=False),
                        energy_cyclical=MarketMonitorLayerMetric(score=50, delta_5d=0.0, preferred=False),
                        financials=MarketMonitorLayerMetric(score=50, delta_5d=0.0, preferred=False),
                        preferred_assets=[],
                        avoid_assets=[],
                    ),
                ),
            )

        self.assertEqual(result.payload.tactic_layer.top_tactic, "回调低吸")
        self.assertEqual(result.payload.asset_layer.preferred_assets, ["防御板块", "能源/周期"])
        self.assertEqual(result.trace.card_type, "style")

    def test_panic_inference_falls_back_when_json_invalid(self) -> None:
        with patch(
            "tradingagents.web.market_monitor.inference.base.create_llm_client",
            return_value=type("_FakeClient", (), {"get_llm": lambda self: _FakeLlm("invalid")})(),
        ):
            service = MarketMonitorCardInferenceService()
            result = service.infer_panic(
                self._build_fact_sheet(),
                fallback=lambda: MarketMonitorPanicCard(
                    score=41.2,
                    zone="观察期",
                    state="panic_watch",
                    panic_extreme_score=38.0,
                    selling_exhaustion_score=45.0,
                    reversal_confirmation_score=39.0,
                    action="加入观察列表，等待确认。",
                    stop_loss="ATR×1.0",
                    profit_rule="达 1R 兑现 50%，余仓移止损到成本线。",
                    timeout_warning=False,
                    days_held=0,
                    early_entry_allowed=False,
                    max_position_hint="20%-35%",
                ),
            )

        self.assertTrue(result.used_fallback)
        self.assertEqual(result.payload.state, "panic_watch")
        self.assertFalse(result.trace.parsed_ok)
        self.assertEqual(result.trace.card_type, "panic")


if __name__ == "__main__":
    unittest.main()
