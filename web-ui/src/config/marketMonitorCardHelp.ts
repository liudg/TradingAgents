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
      "模型先读取本地价格、均线、区间位置、ETF proxy 广度与进攻/防御相对强弱，再在必要时补充搜索背景，输出偏多、中性或偏空结论。",
  },
  short_term_card: {
    title: "短线环境",
    purpose: "判断当前刷新时点的短线交易窗口是否友好，以及更适合等待、低吸还是顺势参与。",
    rules:
      "模型结合行业 ETF 动量扩散、波动和事件背景，直接基于当前可见数据给出短线可做性结论与动作建议。",
  },
  system_risk_card: {
    title: "系统风险",
    purpose: "衡量系统性风险是否显著抬升，以及是否需要收紧风险预算。",
    rules:
      "模型优先读取 VIX、LQD/JNK、IWM/SPY、ARKK/SPY 等代理指标，再补充外部风险事件，输出正常、承压或高风险判断。",
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
      "页面直接展示 regime、总仓位、动作开关、单票上限与风险预算，并用观察次数表达风险放宽解锁条件。",
  },
  event_risk_card: {
    title: "事件风险",
    purpose: "识别当前刷新时点已知、可能收紧执行权限的宏观或财报事件。",
    rules:
      "模型在需要时搜索官方日历、公司公告与主流财经媒体；若缺少搜索事实，则保守降级，只允许收紧执行权限而不放宽风险边界。",
  },
  panic_card: {
    title: "恐慌模块",
    purpose: "识别是否存在基于当前指数、ETF 与波动率行为的可交易反转机会。",
    rules:
      "模型结合指数、ETF、高 beta basket 与波动率的当前刷新数据判断是否进入恐慌反转窗口，只基于当下可见证据输出结论。",
  },
};
