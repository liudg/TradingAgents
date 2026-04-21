from __future__ import annotations

import json
from typing import Any

from tradingagents.web.market_monitor.schemas import MarketMonitorFactSheet


def _compact_fact_sheet(fact_sheet: MarketMonitorFactSheet) -> str:
    payload: dict[str, Any] = {
        "as_of_date": fact_sheet.as_of_date.isoformat(),
        "derived_metrics": fact_sheet.derived_metrics,
        "market_proxies": fact_sheet.local_facts.get("market_proxies", {}),
        "symbols": fact_sheet.local_facts.get("symbols", {}),
        "open_gaps": fact_sheet.open_gaps,
        "notes": fact_sheet.notes,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_long_term_prompt(fact_sheet: MarketMonitorFactSheet) -> tuple[str, str, str]:
    system_prompt = (
        "你是美股市场监控长线环境裁决器。"
        "你只能基于给定 fact sheet 输出严格 JSON。"
        "不要编造额外数据；如果数据不足，必须在 risks 中说明。"
        "输出字段必须包含: score, zone, delta_1d, delta_5d, slope_state, summary, action, recommended_exposure, reasoning_summary, key_drivers, risks, confidence。"
    )
    user_prompt = f"请根据以下 fact sheet 评估长线环境卡，并只返回 JSON:\n{_compact_fact_sheet(fact_sheet)}"
    return system_prompt, user_prompt, "long_term facts"


def build_system_risk_prompt(fact_sheet: MarketMonitorFactSheet) -> tuple[str, str, str]:
    system_prompt = (
        "你是美股市场监控系统风险裁决器。"
        "你只能基于给定 fact sheet 输出严格 JSON。"
        "输出字段必须包含: score, zone, delta_1d, delta_5d, slope_state, summary, action, liquidity_stress_score, risk_appetite_score, pcr_percentile, pcr_absolute, pcr_panic_flag, reasoning_summary, key_drivers, risks, confidence。"
    )
    user_prompt = f"请根据以下 fact sheet 评估系统风险卡，并只返回 JSON:\n{_compact_fact_sheet(fact_sheet)}"
    return system_prompt, user_prompt, "system_risk facts"


def build_event_risk_prompt(fact_sheet: MarketMonitorFactSheet) -> tuple[str, str, str]:
    system_prompt = (
        "你是美股市场监控事件风险裁决器。"
        "你只能基于给定 fact sheet 输出严格 JSON。"
        "输出字段必须包含: index_level, stock_level, reasoning_summary, key_drivers, risks, confidence。"
        "index_level 需包含 active/type/days_to_event/action_modifier；stock_level 需包含 earnings_stocks/rule。"
    )
    user_prompt = f"请根据以下 fact sheet 评估事件风险卡，并只返回 JSON:\n{_compact_fact_sheet(fact_sheet)}"
    return system_prompt, user_prompt, "event_risk facts"


def build_short_term_prompt(fact_sheet: MarketMonitorFactSheet) -> tuple[str, str, str]:
    system_prompt = (
        "你是美股市场监控短线环境裁决器。"
        "你只能基于给定 fact sheet 输出严格 JSON。"
        "输出字段必须包含: score, zone, delta_1d, delta_5d, slope_state, summary, action, reasoning_summary, key_drivers, risks, confidence。"
    )
    user_prompt = f"请根据以下 fact sheet 评估短线环境卡，并只返回 JSON:\n{_compact_fact_sheet(fact_sheet)}"
    return system_prompt, user_prompt, "short_term facts"


def build_style_prompt(fact_sheet: MarketMonitorFactSheet) -> tuple[str, str, str]:
    system_prompt = (
        "你是美股市场监控风格有效性裁决器。"
        "你只能基于给定 fact sheet 输出严格 JSON。"
        "输出字段必须包含: tactic_layer, asset_layer, reasoning_summary, key_drivers, risks, confidence。"
    )
    user_prompt = f"请根据以下 fact sheet 评估风格有效性卡，并只返回 JSON:\n{_compact_fact_sheet(fact_sheet)}"
    return system_prompt, user_prompt, "style facts"


def build_panic_prompt(fact_sheet: MarketMonitorFactSheet) -> tuple[str, str, str]:
    system_prompt = (
        "你是美股市场监控恐慌反转裁决器。"
        "你只能基于给定 fact sheet 输出严格 JSON。"
        "输出字段必须包含: score, zone, state, panic_extreme_score, selling_exhaustion_score, reversal_confirmation_score, action, system_risk_override, stop_loss, profit_rule, timeout_warning, days_held, early_entry_allowed, max_position_hint, reasoning_summary, key_drivers, risks, confidence。"
    )
    user_prompt = f"请根据以下 fact sheet 评估恐慌反转卡，并只返回 JSON:\n{_compact_fact_sheet(fact_sheet)}"
    return system_prompt, user_prompt, "panic facts"
