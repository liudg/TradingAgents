from __future__ import annotations

import json
from typing import Any

from tradingagents.web.market_monitor.schemas import (
    MarketMonitorEventFact,
    MarketMonitorFactSheet,
    MarketMonitorPanicCard,
    MarketMonitorScoreCard,
    MarketMonitorStyleEffectiveness,
    MarketMonitorSystemRiskCard,
)


CONFLICT_MATRIX: list[dict[str, Any]] = [
    {"when": {"system_risk": "[60,70)"}, "regime_label": "橙灯", "rules": ["系统风险 override", "禁止杠杆", "降低新开仓权限"]},
    {"when": {"system_risk": "[70,80)"}, "regime_label": "红灯-高压", "rules": ["只允许对冲或极低风险仓位"]},
    {"when": {"system_risk": "[80,100]"}, "regime_label": "红灯-危机", "rules": ["危机模式", "只保留对冲或极低风险仓位"]},
    {"when": {"long_term": "[80,100]", "short_term": "[65,100]", "system_risk": "[0,25)"}, "regime_label": "绿灯", "rules": ["允许 80%-100% 总仓", "追高和隔夜允许"]},
    {"when": {"long_term": "[65,80)", "short_term": "[55,100]", "system_risk": "[0,60)"}, "regime_label": "黄绿灯/黄灯", "rules": ["进攻但按系统风险控制权限"]},
    {"when": {"long_term": "[45,65)", "short_term": "[60,100]", "system_risk": "[0,35)"}, "regime_label": "黄绿灯-Swing", "rules": ["允许积极 swing", "不建趋势重仓"]},
    {"when": {"long_term": "[0,45)", "short_term": "[0,45)"}, "regime_label": "红灯", "rules": ["净值保护", "禁一切新开仓"]},
]

EVENT_RISK_RULES: dict[str, Any] = {
    "index_level": ["指数级事件影响整体 regime 权限", "只能收紧，不能放宽风险边界"],
    "stock_level": ["个股级事件只影响该股", "不得污染指数 regime label"],
}

SIGNAL_CONFIRMATION_RULES: dict[str, Any] = {
    "risk_tightening_rule": "风险收紧触发1次即生效",
    "risk_loosening_rule": "风险放宽需连续3次刷新保持后才放宽",
    "panic_exception": "panic_confirmed 可豁免主评分卡3次风险放宽确认，但仓位独立管理",
}


def build_execution_prompt(
    fact_sheet: MarketMonitorFactSheet,
    long_term: MarketMonitorScoreCard,
    short_term: MarketMonitorScoreCard,
    system_risk: MarketMonitorSystemRiskCard,
    style: MarketMonitorStyleEffectiveness,
    panic: MarketMonitorPanicCard,
    event_fact_sheet: list[MarketMonitorEventFact],
) -> tuple[str, str, str]:
    system_prompt = (
        "你是美股市场监控执行动作卡聚合器。"
        "你只能基于给定评分卡、统一 event_fact_sheet 和固定优先级输出严格 JSON。"
        "执行卡不得重新搜索、不得私自修改事件事实、不得重算单卡因子。"
        "系统风险 override 最高优先级，system_risk_score 位于 [60,70)、[70,80)、[80,100] 时必须按规则收紧。"
        "panic 仓位独立于趋势仓和 swing 仓，不得把 panic_confirmed 解读为趋势仓恢复。"
        "事件风险只允许收紧执行权限；个股级事件不得污染指数 regime。"
        "输出字段必须包含: regime_label, conflict_mode, total_exposure_range, new_position_allowed, chase_breakout_allowed, dip_buy_allowed, overnight_allowed, leverage_allowed, single_position_cap, daily_risk_budget, tactic_preference, preferred_assets, avoid_assets, signal_confirmation, event_risk_flag, reasoning_summary, key_drivers, risks, evidence, confidence。"
    )
    payload: dict[str, Any] = {
        "decision_framework": {
            "conflict_matrix": CONFLICT_MATRIX,
            "event_risk_rules": EVENT_RISK_RULES,
            "signal_confirmation_rules": SIGNAL_CONFIRMATION_RULES,
        },
        "fact_sheet": {
            "as_of_date": fact_sheet.as_of_date.isoformat(),
            "open_gaps": fact_sheet.open_gaps,
            "derived_metrics": fact_sheet.derived_metrics,
        },
        "event_fact_sheet": [event.model_dump(mode="json") for event in event_fact_sheet],
        "long_term_score": long_term.model_dump(mode="json"),
        "short_term_score": short_term.model_dump(mode="json"),
        "system_risk_score": system_risk.model_dump(mode="json"),
        "style_effectiveness": style.model_dump(mode="json"),
        "panic_reversal_score": panic.model_dump(mode="json"),
    }
    user_prompt = f"请根据以下结构化输入生成执行动作卡，并只返回 JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    return system_prompt, user_prompt, "execution decision facts"
