from __future__ import annotations

import json
from typing import Any

from tradingagents.web.market_monitor.schemas import (
    MarketMonitorEventRiskFlag,
    MarketMonitorFactSheet,
    MarketMonitorScoreCard,
    MarketMonitorStyleEffectiveness,
    MarketMonitorSystemRiskCard,
)


CONFLICT_MATRIX: list[dict[str, Any]] = [
    {
        "when": {"long_term_min": 65, "short_term_min": 55, "system_risk_max": 35},
        "regime_label": "绿灯",
        "conflict_mode": "长强短强-顺势进攻",
        "rules": ["满仓进攻", "允许追高", "允许隔夜"],
    },
    {
        "when": {"long_term_min": 65, "short_term_min": 55, "system_risk_min_exclusive": 35, "system_risk_max": 60},
        "regime_label": "黄灯",
        "conflict_mode": "长强短强-风险中等",
        "rules": ["进攻但控制单票上限", "减杠杆"],
    },
    {
        "when": {"long_term_min": 65, "short_term_max_exclusive": 45},
        "regime_label": "黄灯-等待",
        "conflict_mode": "长强短弱-等待修复",
        "rules": ["趋势仓不减", "禁追高", "只允许低吸"],
    },
    {
        "when": {"long_term_min": 65, "short_term_max_exclusive": 25},
        "regime_label": "橙灯",
        "conflict_mode": "长强极弱-等待恐慌修复",
        "rules": ["趋势仓保持", "禁所有新开仓", "等待恐慌反转确认"],
    },
    {
        "when": {"long_term_min": 45, "long_term_max_exclusive": 65, "short_term_min": 60, "system_risk_max": 35},
        "regime_label": "黄绿灯-Swing",
        "conflict_mode": "长线中性+短线活跃+风险低",
        "rules": ["允许积极 swing", "允许追强势股", "不建趋势重仓"],
    },
    {
        "when": {"long_term_min": 45, "long_term_max_exclusive": 65, "short_term_min": 45, "short_term_max_exclusive": 55, "system_risk_max": 50},
        "regime_label": "黄灯",
        "conflict_mode": "中性环境-低频参与",
        "rules": ["低频操作", "低吸+确认突破", "不提高频率"],
    },
    {
        "when": {"long_term_min": 45, "long_term_max_exclusive": 65, "short_term_max_exclusive": 45},
        "regime_label": "橙灯",
        "conflict_mode": "中性转弱-控仓防守",
        "rules": ["控仓", "防守为主"],
    },
    {
        "when": {"long_term_max_exclusive": 45, "short_term_min": 55, "system_risk_max": 35},
        "regime_label": "黄灯-短线",
        "conflict_mode": "长弱短强-仅短线博弈",
        "rules": ["只允许短线博弈仓", "不建趋势仓", "单票上限减半", "日内优先"],
    },
    {
        "when": {"long_term_max_exclusive": 45, "short_term_max_exclusive": 45},
        "regime_label": "红灯",
        "conflict_mode": "双弱-净值保护",
        "rules": ["禁一切新开仓", "净值保护优先"],
    },
    {
        "when": {"system_risk_min_exclusive": 70},
        "regime_label": "红灯",
        "conflict_mode": "系统风险高压-危机模式",
        "rules": ["只保对冲", "杠杆全清"],
    },
]

EVENT_RISK_RULES: dict[str, Any] = {
    "index_level": [
        "指数级事件可收紧执行权限，但不能改写上游事实",
        "指数级事件可限制 new_position_allowed / overnight_allowed / single_position_cap",
    ],
    "stock_level": [
        "个股级事件只影响该股，不污染 regime_label",
        "财报季密集期只做个股标记，不改变指数 regime",
    ],
}

SIGNAL_CONFIRMATION_RULES: dict[str, Any] = {
    "risk_tightening_rule": "风险收紧信号立即生效",
    "risk_loosening_rule": "风险放宽需连续 3 次刷新保持后才解锁",
    "default_assumption": "若没有历史持续观测，默认 current_regime_observations=1，并据此推算 risk_loosening_unlock_in_observations",
}


def build_execution_prompt(
    fact_sheet: MarketMonitorFactSheet,
    long_term: MarketMonitorScoreCard,
    short_term: MarketMonitorScoreCard,
    system_risk: MarketMonitorSystemRiskCard,
    style: MarketMonitorStyleEffectiveness,
    event_risk: MarketMonitorEventRiskFlag,
) -> tuple[str, str, str]:
    system_prompt = (
        "你是美股市场监控执行动作卡聚合器。"
        "你只能基于给定结构化卡片和 fact sheet 输出严格 JSON。"
        "不要重写上游事实，只根据长线、短线、系统风险、风格、事件风险给出执行结论。"
        "本地结构化市场数据优先，搜索结果只能补充事件、背景和叙事，不能覆盖本地量化指标。"
        "若引用搜索信息，必须保持可溯源，并优先采用官方日历、公司公告与主流财经媒体。"
        "你必须严格遵守输入中的冲突矩阵、事件分离规则、风险收紧/风险放宽规则；若模型判断与规则冲突，以规则为准。"
        "个股级事件只影响个股执行限制，不能污染 regime_label。"
        "指数级事件只允许收紧执行权限，不能放宽风险边界。"
        "若数据不足，只能在 risks 说明，不能编造缺失事实。"
        "输出字段必须包含: regime_label, conflict_mode, total_exposure_range, new_position_allowed, chase_breakout_allowed, dip_buy_allowed, overnight_allowed, leverage_allowed, single_position_cap, daily_risk_budget, tactic_preference, preferred_assets, avoid_assets, signal_confirmation, event_risk_flag, summary, reasoning_summary, key_drivers, risks, confidence。"
        "signal_confirmation 必须包含 current_regime_observations, risk_loosening_unlock_in_observations, note。"
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
        "long_term": long_term.model_dump(mode="json"),
        "short_term": short_term.model_dump(mode="json"),
        "system_risk": system_risk.model_dump(mode="json"),
        "style": style.model_dump(mode="json"),
        "event_risk": event_risk.model_dump(mode="json"),
    }
    user_prompt = f"请根据以下结构化输入生成执行动作卡，并只返回 JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    return system_prompt, user_prompt, "execution aggregation facts"
