export type MarketMonitorCardHelpKey =
  | "long_term_card"
  | "short_term_card"
  | "system_risk_card"
  | "style_effectiveness_card"
  | "execution_card"
  | "event_risk_card"
  | "panic_card";

export type MarketMonitorCardHelpContent = {
  title: string;
  purpose: string;
  rules: string;
};

export const MARKET_MONITOR_CARD_HELP: Record<
  MarketMonitorCardHelpKey,
  MarketMonitorCardHelpContent
> = {
  long_term_card: {
    title: "长线环境",
    purpose: "判断中期市场环境是否支持继续维持或增加趋势仓位。",
    rules:
      "模型先读取本地价格、均线、区间位置、广度代理等结构化数据，再搜索缺失的宏观与市场上下文，综合输出偏多、中性或偏空结论。",
  },
  short_term_card: {
    title: "短线环境",
    purpose: "判断短线交易窗口是否友好，以及更适合等待、低吸还是顺势参与。",
    rules:
      "模型结合本地动量、波动、广度代理与外部事件背景，给出短线可做性结论与动作建议。",
  },
  system_risk_card: {
    title: "系统风险",
    purpose: "衡量系统性风险是否显著抬升，以及是否需要收紧风险预算。",
    rules:
      "模型优先读取 VIX、大小盘相对表现和代理广度，再补充外部风险事件，输出正常、承压或高风险判断。",
  },
  style_effectiveness_card: {
    title: "风格有效性",
    purpose: "判断当前更适合哪种手法，以及哪些资产方向更值得优先关注。",
    rules:
      "页面分为策略手法层和资产风格层两部分，分别展示最佳手法、回避手法、偏好资产与回避资产。",
  },
  execution_card: {
    title: "执行动作卡",
    purpose: "把市场判断翻译成仓位、追高、低吸、隔夜和杠杆等可执行动作。",
    rules:
      "页面直接展示 regime、总仓位、动作开关、单票上限与风险预算，不再围绕旧的运行轨迹结果做映射。",
  },
  event_risk_card: {
    title: "事件风险",
    purpose: "识别未来几个交易日可能影响指数和风格轮动的宏观或财报事件。",
    rules:
      "模型固定先搜索未来三日重要宏观事件和财报日历，再判断事件是否足以改变执行层建议。",
  },
  panic_card: {
    title: "恐慌模块",
    purpose: "识别是否存在恐慌后的可交易反转机会。",
    rules:
      "模型结合本地波动和外部风险背景判断是否存在恐慌反转窗口；若证据不足，会明确保持未激活结论。",
  },
};
