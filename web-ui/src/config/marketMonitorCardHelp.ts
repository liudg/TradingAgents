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
    purpose: "判断中期趋势、ETF proxy 广度、风险偏好与波动健康度是否支持持有风险资产。",
    rules:
      "V2.3.1 先由本地 yfinance 数据确定性计算基础分和因子拆解，LLM 只能解释、标注风险，并在事件事实表支持下做受限评分调整。",
  },
  short_term_card: {
    title: "短线环境",
    purpose: "判断未来 1-5 个刷新周期内是否适合主动交易，以及低吸、突破和事件交易权限。",
    rules:
      "日线模式不得使用盘中语言；行业 ETF 动量、突破延续、风格参与和波动友好度由规则层计算，LLM 不覆盖本地量化指标。",
  },
  system_risk_card: {
    title: "系统风险",
    purpose: "衡量流动性压力和风险偏好恶化程度，并作为执行卡最高优先级 override。",
    rules:
      "系统风险分越高越危险；斜率文案必须使用风险上升/回落语义，不能把风险分上升描述为改善。",
  },
  style_effectiveness_card: {
    title: "市场手法与风格有效性",
    purpose: "判断当前更适合趋势突破、回调低吸还是超跌反弹，并识别市场偏好的资产风格。",
    rules:
      "ETF proxy 只能表达市场手法和资产风格偏好，不能直接代表个股交易胜率。",
  },
  execution_card: {
    title: "执行动作卡",
    purpose: "按系统风险、长线、短线、风格、事件风险和 panic 独立豁免顺序生成最终动作。",
    rules:
      "系统风险 override 最高；风险收紧一次生效，风险放宽需连续三次刷新确认；panic 仓位独立管理。",
  },
  event_risk_card: {
    title: "事件风险",
    purpose: "展示统一 event_fact_sheet 对执行权限的影响。",
    rules:
      "执行卡只能消费统一事件事实表，不得重新搜索或保留私有事件结论；指数级事件影响整体权限，个股级事件只影响个股。",
  },
  panic_card: {
    title: "恐慌模块",
    purpose: "区分恐慌是否充分和反弹是否确认，寻找独立反弹策略仓机会。",
    rules:
      "panic_extreme_score 高只代表恐慌强，不等于反转确认；必须出现抛压衰竭或反弹确认才进入 panic_confirmed。",
  },
};
