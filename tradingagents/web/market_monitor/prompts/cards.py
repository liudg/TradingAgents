from __future__ import annotations

import json
from typing import Any

from tradingagents.web.market_monitor.schemas import (
    MarketMonitorEventRiskFlag,
    MarketMonitorFactSheet,
    MarketMonitorPanicCard,
    MarketMonitorScoreCard,
    MarketMonitorStyleEffectiveness,
    MarketMonitorSystemRiskCard,
)


def _card_payload(fact_sheet: MarketMonitorFactSheet, deterministic_card: Any, rules: dict[str, Any]) -> str:
    payload = {
        "fact_sheet": {
            "as_of_date": fact_sheet.as_of_date.isoformat(),
            "derived_metrics": fact_sheet.derived_metrics,
            "market_proxies": fact_sheet.local_facts.get("market_proxies", {}),
            "symbols": fact_sheet.local_facts.get("symbols", {}),
            "event_fact_sheet": [event.model_dump(mode="json") for event in fact_sheet.event_fact_sheet],
            "evidence": [ref.model_dump(mode="json") for ref in fact_sheet.evidence],
            "open_gaps": fact_sheet.open_gaps,
            "notes": fact_sheet.notes,
        },
        "deterministic_card": deterministic_card.model_dump(mode="json"),
        "rules": rules,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _system_prompt(card_name: str, required_fields: str) -> str:
    return (
        f"你是美股市场监控 {card_name} 裁决器。"
        "你只能基于给定 deterministic_card 与统一 event_fact_sheet 输出严格 JSON。"
        "deterministic_score 与 factor_breakdown 由规则层计算，禁止改写、重算或补写。"
        "本地价格、成交量、波动率、均线、百分位等结构化指标只能来自输入，禁止编造。"
        "event_fact_sheet 只能用于事件、叙事、风险说明和受限 score_adjustment。"
        "若没有事件事实，不得虚构宏观日历、财报、政策或地缘事件。"
        "score_adjustment 必须为 null，除非它引用 event_fact_sheet 中有效且未过期的 event_id；默认幅度必须在 ±5 内，source_event_ids 不得为空，expires_at 不得晚于来源事件过期时间，并写明 confidence。"
        "输出必须保留 deterministic_card 的结构和基础分，只允许补充 reasoning_summary、key_drivers、risks、evidence、confidence，并在规则允许范围内调整最终 score。"
        f"输出字段必须包含: {required_fields}。"
    )


def build_long_term_prompt(fact_sheet: MarketMonitorFactSheet, deterministic_card: MarketMonitorScoreCard) -> tuple[str, str, str]:
    rules = {
        "score_direction": "long_term_score 越高代表长线环境越友好",
        "allowed_adjustment": "默认不调整；只有 event_fact_sheet 中指数级事件显著影响中期风险时才可在 ±5 内调整",
        "data_mode_rule": "daily 模式不得使用盘中语言",
    }
    fields = "deterministic_score, score, zone, delta_1d, delta_5d, slope_state, recommended_exposure, factor_breakdown, score_adjustment, reasoning_summary, key_drivers, risks, evidence, confidence"
    return _system_prompt("长线环境卡", fields), f"请根据以下输入返回长线环境卡 JSON:\n{_card_payload(fact_sheet, deterministic_card, rules)}", "long_term deterministic factors"


def build_short_term_prompt(fact_sheet: MarketMonitorFactSheet, deterministic_card: MarketMonitorScoreCard) -> tuple[str, str, str]:
    rules = {
        "score_direction": "short_term_score 越高代表短线交易环境越友好",
        "allowed_adjustment": "默认不调整；只有已规范化事件影响 1-5 个刷新周期交易环境时才可在 ±5 内调整",
        "data_mode_rule": "daily 模式不得使用刷新时高低点、尾盘回收率等盘中语言",
    }
    fields = "deterministic_score, score, zone, delta_1d, delta_5d, slope_state, factor_breakdown, score_adjustment, reasoning_summary, key_drivers, risks, evidence, confidence"
    return _system_prompt("短线环境卡", fields), f"请根据以下输入返回短线环境卡 JSON:\n{_card_payload(fact_sheet, deterministic_card, rules)}", "short_term deterministic factors"


def build_system_risk_prompt(fact_sheet: MarketMonitorFactSheet, deterministic_card: MarketMonitorSystemRiskCard) -> tuple[str, str, str]:
    rules = {
        "score_direction": "system_risk_score 越高代表系统风险越高、越危险",
        "wording_rule": "风险分上升必须描述为风险上升，不得描述为改善",
        "allowed_adjustment": "只有 event_fact_sheet 中高严重度指数级事件或本地确定性触发器可在 ±5 内调高风险",
    }
    fields = "deterministic_score, score, zone, liquidity_stress_score, risk_appetite_score, delta_1d, delta_5d, slope_state, factor_breakdown, event_triggers, score_adjustment, reasoning_summary, key_drivers, risks, evidence, confidence"
    return _system_prompt("系统风险卡", fields), f"请根据以下输入返回系统风险卡 JSON:\n{_card_payload(fact_sheet, deterministic_card, rules)}", "system_risk deterministic factors"


def build_style_prompt(fact_sheet: MarketMonitorFactSheet, deterministic_card: MarketMonitorStyleEffectiveness) -> tuple[str, str, str]:
    rules = {
        "score_direction": "style_effectiveness 越高代表对应手法或资产风格越有效",
        "scope_rule": "ETF proxy 只能表达市场手法和资产风格偏好，不能直接代表个股交易胜率",
        "allowed_adjustment": "风格卡不直接调整基础因子分，只补充解释、风险和置信度",
    }
    fields = "tactic_layer, asset_layer, reasoning_summary, key_drivers, risks, evidence, confidence"
    return _system_prompt("市场手法与风格有效性卡", fields), f"请根据以下输入返回风格有效性卡 JSON:\n{_card_payload(fact_sheet, deterministic_card, rules)}", "style deterministic factors"


def build_event_risk_prompt(fact_sheet: MarketMonitorFactSheet, deterministic_card: MarketMonitorEventRiskFlag) -> tuple[str, str, str]:
    rules = {
        "event_source_rule": "只能消费统一 event_fact_sheet，不得重新搜索或添加私有事件事实",
        "index_vs_stock_rule": "指数级事件影响整体 regime 权限；个股级事件只影响该股",
    }
    fields = "index_level, stock_level"
    return _system_prompt("事件风险卡", fields), f"请根据以下输入返回事件风险 JSON:\n{_card_payload(fact_sheet, deterministic_card, rules)}", "event_fact_sheet"


def build_panic_prompt(fact_sheet: MarketMonitorFactSheet, deterministic_card: MarketMonitorPanicCard) -> tuple[str, str, str]:
    rules = {
        "score_direction": "panic_extreme_score 越高只代表恐慌越强；panic_reversal_score 越高代表反弹机会越强",
        "state_machine": "capitulation_watch 不能仅因恐慌更强升级为 panic_confirmed；panic_confirmed 必须满足抛压衰竭或反弹确认门槛",
        "data_mode_rule": "daily 模式只能用日线 OHLCV proxy，不得声称盘中实时低点或尾盘回收",
    }
    fields = "score, zone, state, panic_extreme_score, selling_exhaustion_score, intraday_reversal_score, factor_breakdown, action, system_risk_override, stop_loss, profit_rule, timeout_warning, refreshes_held, early_entry_allowed, max_position_hint, reasoning_summary, key_drivers, risks, evidence, confidence"
    return _system_prompt("恐慌反转卡", fields), f"请根据以下输入返回恐慌反转卡 JSON:\n{_card_payload(fact_sheet, deterministic_card, rules)}", "panic deterministic factors"
