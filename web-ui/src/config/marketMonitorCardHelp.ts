export type MarketMonitorCardHelpKey =
  | "panic_module"
  | "long_term_score"
  | "short_term_score"
  | "system_risk_score"
  | "model_overlay"
  | "rule_snapshot";

export type MarketMonitorCardHelpContent = {
  title: string;
  purpose: string;
  rules: string;
};

export const MARKET_MONITOR_CARD_HELP: Record<
  MarketMonitorCardHelpKey,
  MarketMonitorCardHelpContent
> = {
  panic_module: {
    title: "恐慌模块",
    purpose:
      "用于识别美股是否进入恐慌后的可交易反转窗口，帮助区分仅需观察的极端波动与允许轻仓试错的确认反弹。",
    rules:
      "综合 panic_extreme_score、selling_exhaustion_score 与反转确认分数得出结论。极端恐慌分优先决定是否进入 watch 或 confirmed；当综合反转分达到阈值，或强恐慌直接触发时，才给出可执行结论与 early entry 提示。",
  },
  long_term_score: {
    title: "长期规则卡",
    purpose:
      "用于判断中长期市场环境是否支持提升总仓位，核心回答当前更适合防守、试仓还是进攻。",
    rules:
      "按长期趋势结构、市场广度修复、龙头确认和波动健康度四组因子评分后汇总为 0 到 100 分，再映射到防守区、谨慎区、试仓区、进攻区和强趋势区，同时给出 1 日、5 日变化与斜率状态。",
  },
  short_term_score: {
    title: "短期规则卡",
    purpose:
      "用于判断短线交易环境是否友好，帮助确认当前更适合等待、轻仓试错还是积极参与短线机会。",
    rules:
      "基于热点延续性、突破成功率、板块赚钱效应和波动友好度四组因子汇总评分，再映射到极差区、弱势区、观察区、可做区、活跃区和高胜率区，并结合 1 日、5 日变化展示短线环境是否在改善或恶化。",
  },
  system_risk_score: {
    title: "系统风险卡",
    purpose:
      "用于衡量流动性压力与风险偏好是否在同步恶化，决定整体风险预算、杠杆使用和防守优先级。",
    rules:
      "由流动性压力分和风险偏好分各占一半组成，总分越高代表系统风险越大。核心参考 VIX、信用利差、大小盘相对表现、防御板块强弱与跨资产同步下跌等指标，最终映射到低压区、正常区、压力区、高压区和危机区。",
  },
  model_overlay: {
    title: "模型叠加",
    purpose:
      "用于在规则快照之上补充模型视角的市场叙述与风险解释，帮助快速理解当前结论背后的上下文。",
    rules:
      "该卡片本身不直接重新计算规则分数，而是读取模型输出的市场、风险和恐慌叙述，并展示是否应用、置信度、状态覆盖以及证据来源；当模型未应用或出错时，会明确显示跳过或异常状态。",
  },
  rule_snapshot: {
    title: "规则快照",
    purpose:
      "用于展示规则引擎在模型叠加前的基础结论，是页面上其他决策信息的底层确定性快照。",
    rules:
      "汇总基础 regime、基础执行卡、缺失输入和降级因子。结论主要来自长期、短期、系统风险与事件风险规则的组合，不含模型修正；若关键输入缺失，会通过 ready 状态、missing inputs 和 degraded factors 明确标记。",
  },
};
