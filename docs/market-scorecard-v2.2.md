# 美股市场评分卡 V2.2

> 在 V2.1 基础上修复六个核心问题：
> 1. 阈值类型分类（百分位 vs 绝对值）
> 2. panic_trigger 改为计分制 + 两级状态
> 3. 风格有效性卡拆为两层
> 4. 冲突矩阵补充"长线中性+短线强"场景
> 5. 恐慌反转模块豁免3日确认延迟
> 6. 事件风险分指数级/个股级两层

---

## 0. 实现方式说明

> **重要：本文档描述的因子、权重、阈值和分区表是 LLM 裁决时的参考知识框架，而非代码中硬编码实现的计算规则。**

### 0.1 多阶段 LLM 管线架构

代码实现（`tradingagents/web/market_monitor/service.py`）采用 **LLM 多阶段管线**，而非按规则计算分数：

1. **input_bundle** — 拉取本地市场数据（OHLCV + 技术指标），构建市场快照
2. **search_slots** — LLM 使用 web_search 工具，按 5 个槽位（宏观日历、财报关注、政策地缘、风险情绪、市场结构）补充缺失信息
3. **fact_sheet** — 整合本地数据事实 + 搜索事实，构建事实表与证据索引
4. **judgment_group_a** — LLM 基于事实表生成**长线环境**与**系统风险**裁决卡
5. **judgment_group_b** — LLM 基于事实表生成**短线环境**、**事件风险**与**恐慌**裁决卡
6. **execution_decision** — LLM 综合所有裁决卡生成执行建议

### 0.2 本文档的定位

- 下文各节（因子量化映射、分区表、冲突矩阵等）定义了 LLM 在裁决时**应参考的领域知识和决策框架**
- LLM 在生成裁决时应覆盖文档定义的关键维度，但可根据实际数据可用性和市场情况灵活调整
- 分区表和动作映射为 LLM 输出 label 和 action 提供标准化参考
- Prompt 设计应将本文档的核心规则编入 system instructions 或 fact sheet 上下文

### 0.3 当前实现的额外特性（文档外）

以下特性已在代码中实现，但不属于本评分卡框架定义范围：

- **Prompt 审计追踪**：每次 LLM 调用的完整输入/输出持久化（PromptCaptureStore）
- **运行阶段持久化与恢复**：各阶段状态落盘，服务重启时自动标记未完成的运行为失败
- **LLM 并发限制与超时保护**：BoundedSemaphore + 硬超时守护线程
- **证据索引**：搜索结果关联到事实表，支持前端溯源展示

---

## 1. 全局数据标准化原则（修订版）

### 1.1 三类因子，三种阈值策略

V2.1 的"全部百分位化"方向正确但过头。正确分类如下：

| 因子类型 | 特征 | 适合方法 | 典型例子 |
|---|---|---|---|
| **慢变量 / 水位型** | 反映结构性压力水位，缓慢漂移 | 252日滚动百分位 | VIX绝对水平、IG信用利差水位、PCR均值 |
| **事件型 / 速度型** | 反映单日冲击强度，离散触发 | 绝对阈值或半绝对阈值 | VIX单日涨幅、指数单日跌幅、隔夜缺口幅度 |
| **混合型** | 既有水位意义，又有极值触发意义 | 百分位 + 绝对阈值双重判断 | PCR（水位→风险分；极值→触发恐慌模块）|

```python
# 慢变量：252日百分位标准化
def to_percentile_score(series: pd.Series, current_value: float) -> float:
    return percentileofscore(series.dropna(), current_value)  # 返回 0-100

# 事件型：直接用绝对阈值
def is_vix_spike(vix_1d_change: float) -> bool:
    return vix_1d_change > 0.20  # VIX单日涨幅 > 20%

# 混合型：两路并行
def pcr_handler(pcr_current, pcr_series):
    pcr_pct = to_percentile_score(pcr_series, pcr_current)  # 慢变量路径→风险分
    panic_flag = pcr_current > 1.5  # 绝对阈值路径→恐慌触发
    return pcr_pct, panic_flag
```

### 1.2 变化量与斜率状态

```python
delta_1d = score_today - score_yesterday
delta_5d = score_today - score_5d_ago

def slope_state(delta_1d, delta_5d):
    if delta_1d > 3  and delta_5d > 8:   return "加速改善"
    if delta_1d > 0  and delta_5d > 3:   return "缓慢改善"
    if abs(delta_1d) <= 2:               return "钝化震荡"
    if delta_1d < 0  and delta_5d < -3:  return "缓慢恶化"
    if delta_1d < -3 and delta_5d < -8:  return "加速恶化"
    return "震荡"
```

---

## 2. 长线环境卡

### 2.1 因子量化映射（LLM 参考框架）

> 以下因子和权重供 LLM 裁决时参考，非代码硬编码计算。

**趋势结构（权重 35%）**

| 因子 | 计算方法 | 评分规则 |
|---|---|---|
| SPY 与 200 日均线关系 | (close - MA200) / MA200 | **阶梯分**：偏离 >+3% → 25分；0~+3% → 18分；-2%~0 → 10分；<-2% → 0分 |
| SPY 50 日均线斜率 | MA50_today - MA50_20d_ago | 252日百分位 → 0-25分 |
| SPY 相对 3 月区间位置 | (close - 3m_low) / (3m_high - 3m_low) × 25 | 连续分 0-25分 |
| QQQ 与 SPY 趋势同步性 | 两者 20日收益率方向 | 同向上升 → 25分；分歧 → 12分；同降 → 0分 |

**广度修复（权重 25%）**

| 因子 | 计算方法 | 评分规则 |
|---|---|---|
| 站上 200日均线股票占比 | 个股日线扫描 | 252日百分位 → 0-40分 |
| 52周新高 - 新低净差值 | 广度数据 | 252日百分位 → 0-35分 |
| NYSE 累积 A/D 线 20日斜率 | MarketCharts | **阶梯分**：上升斜率>0且加速 → 25分；上升但放缓 → 15分；持平 → 8分；下降 → 0分 |

**龙头确认（权重 20%）**

| 因子 | 计算方法 | 评分规则 |
|---|---|---|
| RS Line 创新高股票占比 | 个股 RS vs SPY，252日百分位 | 连续分 0-50分 |
| 强势股（RS>1.2）近10日净新高数 | 正/负/中性 | **阶梯分**：净新高 >20 → 50分；1~20 → 30分；-10~0 → 15分；<-10 → 0分 |

**波动健康度（权重 20%）**

| 因子 | 计算方法 | 评分规则 |
|---|---|---|
| VIX 水位（慢变量） | 252日百分位，反向 | 100 - VIX_pct → 0-50分 |
| VIX 期限结构（VIX3M/VIX）| 比值 | **阶梯分**：>1.10 → 50分；1.00~1.10 → 35分；0.95~1.00 → 15分；<0.95 → 0分 |

### 2.2 分区与动作映射

| 分区 | 分值 | 总仓建议 |
|---|---|---|
| 防守区 | 0-35 | 0%-20% |
| 谨慎区 | 35-50 | 20%-40% |
| 试仓区 | 50-65 | 40%-60% |
| 进攻区 | 65-80 | 60%-80% |
| 强趋势区 | 80-100 | 80%-100% |

---

## 3. 短线环境卡

### 3.1 因子量化映射（LLM 参考框架）

> 以下因子和权重供 LLM 裁决时参考，非代码硬编码计算。

**热点延续性（权重 30%）**

| 因子 | 计算方法 |
|---|---|
| 行业ETF 5日动量 vs 20日动量 | 5日超额动量 >0 的行业数占比 → 252日百分位 |
| 强势股隔夜跳空持续率（近5日）| 前日涨幅>2%股票次日跳空幅度均值 → 252日百分位 |

**突破成功率（权重 25%）**

| 因子 | 计算方法 |
|---|---|
| 20日高突破后3日持续率 | 近10个突破事件：第1-3日正收益率均值 → 0-100分 |
| 放量突破守住率 | 近10次突破：收盘守住突破价次数 / 总次数 |

**板块赚钱效应（权重 25%）**

| 因子 | 计算方法 |
|---|---|
| 尾盘30分钟成交量占比 | 252日百分位（高=机构参与度高）|
| 行业轮动连续性 | 前日强行业次日超额收益 → 近10日均值百分位 |

**波动友好度（权重 20%）**

| 因子 | 计算方法 |
|---|---|
| SPY 日内 ATR% | 252日百分位，**中位数得分最高**（过低=死寂，过高=混乱）→ 倒U型映射 |
| 隔夜缺口质量 | 近5日正向缺口占比 |

### 3.2 分区与动作映射

| 分区 | 分值 | 动作 |
|---|---|---|
| 极差区 | 0-20 | 禁止追涨，只等逆向机会 |
| 弱势区 | 20-35 | 轻仓试错，不隔夜高波动标的 |
| 观察区 | 35-50 | 可观察，不主动进攻 |
| 可做区 | 50-65 | 允许低吸、突破、事件交易 |
| 活跃区 | 65-80 | 允许提高交易频率 |
| 高胜率区 | 80-100 | 短线积极进攻，仍需风控 |

---

## 4. 系统风险卡

### 4.1 两个子分（LLM 参考框架）

> 以下因子和权重供 LLM 裁决时参考，非代码硬编码计算。

**流动性压力分（权重 50%）**

| 因子 | 类型 | 计算方法 | 权重 |
|---|---|---|---|
| VIX 水位 | 慢变量 | 252日百分位 | 30% |
| VVIX/VIX 比值 | 慢变量 | 252日百分位 | 20% |
| IG 信用利差（LQD implied）| 慢变量 | 252日百分位 | 25% |
| HY-IG 利差（JNK vs LQD）| 慢变量 | 252日百分位 | 25% |

**风险偏好分（权重 50%）**

| 因子 | 类型 | 计算方法 | 权重 |
|---|---|---|---|
| IWM/SPY 5日相对表现 | 慢变量 | 252日百分位（低=防御）| 25% |
| XLU/SPY 5日相对表现 | 慢变量 | 252日百分位（高=避险）| 25% |
| 跨资产同步下跌天数（近5日）| 慢变量 | 252日百分位 | 25% |
| PCR 水位 | 混合型 | 252日百分位（→风险分）+ 绝对阈值（→恐慌触发）| 25% |

### 4.2 PCR 双路处理规则

```
慢变量路径（→ 系统风险分）：
  PCR 252日百分位 直接映射到风险偏好分

事件型路径（→ 触发恐慌反转模块，独立于风险分）：
  PCR > 1.5（绝对阈值）      → panic_watch 候选信号
  PCR 百分位 > 90th          → panic_watch 候选信号
  以上任一条件满足 → 传给恐慌模块做综合判断，不直接改变 regime
```

### 4.3 分区与动作映射

| 分区 | 分值 | 动作 |
|---|---|---|
| 低压区 | 0-20 | 允许正常进攻 |
| 正常区 | 20-45 | 常规风控 |
| 压力区 | 45-60 | 缩仓、防追高、降单票风险 |
| 高压区 | 60-80 | 禁止杠杆，优先保护净值 |
| 危机区 | 80-100 | 危机模式，只保留对冲或极低风险仓位 |

---

## 5. 风格有效性卡（重构版：两层拆分）

> V2.1 把"交易手法"和"资产风格"并列在同一层，概念错误。V2.2 拆为两层独立输出，分别回答不同的决策问题。

### 5.1 第一层：策略手法有效性

**回答问题：用什么方式进场？**

| 手法 | 计算方法 | 数据 |
|---|---|---|
| **趋势突破** | 近10日：收盘站上20日高后1-3日正收益率 | 个股日线 |
| **回调低吸** | 近10日：从5日低点买入3日超额收益均值 | SPY + 个股 |
| **超跌反弹** | 近5日：RSI<30股票2日平均反弹幅度 → 252日百分位 | 个股日线 |

输出：`top_tactic`（最佳手法）、`avoid_tactic`（应回避手法）

### 5.2 第二层：资产风格偏好

**回答问题：做哪个方向？**

| 风格 | 计算方法 | 数据 |
|---|---|---|
| **大盘科技** | QQQ vs SPY 10日相对动量 | ETF 日线 |
| **小盘高弹性** | IWM vs SPY 10日相对动量 | ETF 日线 |
| **防御板块** | (XLU+XLV+XLP)/3 vs SPY 10日相对 | ETF 日线 |
| **能源/周期** | (XLE+XLB)/2 vs SPY 10日相对 | ETF 日线 |
| **金融** | XLF vs SPY 10日相对 | ETF 日线 |

输出：`preferred_assets`（相对强势的资产方向）、`avoid_assets`（相对弱势）

### 5.3 两层组合使用示例

```
手法层：趋势突破差，回调低吸好
资产层：防御板块强，小盘弱

→ 执行卡读取：等回调后低吸防御板块ETF，不追涨，不碰小盘
```

### 5.4 输出格式

```json
"style_effectiveness": {
  "tactic_layer": {
    "trend_breakout":  { "score": 28, "valid": false, "delta_5d": -19 },
    "dip_buy":         { "score": 66, "valid": true,  "delta_5d": +11 },
    "oversold_bounce": { "score": 71, "valid": true,  "delta_5d": +26 },
    "top_tactic":   "回调低吸",
    "avoid_tactic": "趋势突破"
  },
  "asset_layer": {
    "large_cap_tech":     { "score": 34, "preferred": false, "delta_5d": -15 },
    "small_cap_momentum": { "score": 19, "preferred": false, "delta_5d": -23 },
    "defensive":          { "score": 81, "preferred": true,  "delta_5d": +22 },
    "energy_cyclical":    { "score": 62, "preferred": true,  "delta_5d": +8  },
    "financials":         { "score": 44, "preferred": false, "delta_5d": -4  },
    "preferred_assets": ["防御板块", "能源/周期"],
    "avoid_assets":     ["小盘高弹性", "大盘科技"]
  }
}
```

---

## 6. 执行动作卡（优化版）

### 6.1 长线/短线冲突处理矩阵（补充完整版）

| 长线 | 短线 | 系统风险 | Regime | 核心规则 |
|---|---|---|---|---|
| 强（≥65）| 强（≥55）| 低（≤35）| 🟢 绿灯 | 满仓进攻，追高允许，隔夜允许 |
| 强（≥65）| 强（≥55）| 中（35-60）| 🟡 黄灯 | 进攻但控单票上限，减杠杆 |
| 强（≥65）| 弱（<45）| 任意 | 🟡 黄灯-等待 | 趋势仓不减，禁追高，只允许低吸，等短线修复 |
| 强（≥65）| 极差（<25）| 任意 | 🟠 橙灯 | 趋势仓保持，禁所有新开仓，等恐慌反转信号 |
| **中性（45-65）**| **强（≥60）**| **低（≤35）**| 🟢 **黄绿灯-Swing** | **允许积极swing，单票上限放宽，允许追强势股；但不建趋势重仓** |
| 中性（45-65）| 中性（45-55）| 正常（≤50）| 🟡 黄灯 | 低频操作，低吸+确认突破，不提高频率 |
| 中性（45-65）| 弱（<45）| 任意 | 🟠 橙灯 | 控仓，防守为主 |
| 弱（<45）| 强（≥55）| 低（≤35）| 🟡 黄灯-短线 | **只允许短线博弈仓**，不建趋势仓，单票上限减半，日内优先 |
| 弱（<45）| 弱（<45）| 任意 | 🔴 红灯 | 净值保护，禁一切新开仓 |
| 任意 | 任意 | 高（>70）| 🔴 红灯 | 危机模式，只保对冲，杠杆全清 |

> **黄绿灯-Swing 场景说明**
>
> 长线中性 + 短线活跃 + 风险低，是美股 swing 交易者最好的赚钱阶段之一。此时指数没有强趋势但行业轮动快，适合做3-10日的强行业波段，不适合做趋势型重仓。执行卡在此场景下应主动放开短线频率，而不是保守等长线信号。

### 6.2 信号确认延迟机制（含恐慌模块豁免）

```
主评分卡（长线/短线/系统风险）：
  升级信号（变严格）：触发1日即生效 → 风险保护优先
  降级信号（变宽松）：需连续3个交易日保持才降级 → 防假突破

恐慌反转模块：完全豁免上述规则
  → 触发即执行，快进快出，不等任何延迟确认
  → 原因：反弹最肥的一段通常在第1-2日，3日确认等于系统性放弃最高赔率入场点
  → 代替延迟机制的是：两级状态（panic_watch / panic_confirmed）作为安全门
```

### 6.3 事件风险层：指数级 vs 个股级分离

**指数级事件（影响整体 regime）**

| 事件 | 前置规则 | 后置规则 |
|---|---|---|
| FOMC 决议日 | T-1 日禁止所有新开仓 | 决议后30分钟观察，再按执行卡正常执行 |
| CPI / PCE 公布 | 当日开盘前禁追高 | 数据后30分钟观察再行动 |
| 非农数据 | 当日禁追高 | 同上 |
| 地缘危机爆发（突发）| 系统风险卡事件型触发，当日禁新开 | 次日重新评估 |

**个股级事件（只影响该股，不污染 regime）**

| 事件 | 规则 |
|---|---|
| 个股财报日（T-1 / T）| 财报前1日该股单票上限减半；财报当日禁追高 |
| 个股重大公告 | 同上 |
| 财报季密集期（每季约2周）| 在个股层面加财报标记，不影响指数regime label |

```json
"event_risk_flag": {
  "index_level": {
    "active": true,
    "type": "FOMC",
    "days_to_event": 1,
    "action_modifier": {
      "new_position_allowed": false,
      "overnight_allowed": false,
      "single_position_cap_multiplier": 0.5,
      "note": "会议前静默期，低波动≠安全"
    }
  },
  "stock_level": {
    "earnings_stocks": ["NVDA", "META"],
    "rule": "上述个股今日单票上限减半，禁追高，不影响regime"
  }
}
```

### 6.4 完整执行卡输出

```json
"execution_card": {
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
  "avoid_assets": ["小盘高弹性", "大盘科技"],
  "signal_confirmation": {
    "current_regime_days": 3,
    "downgrade_unlock_in_days": 0,
    "note": "已满3日，可正常评估降级"
  },
  "event_risk_flag": { ... }
}
```

---

## 7. 恐慌反转捕捉模块（重构版）

### 7.1 两级状态设计

```
panic_watch     → 恐慌已开始，进入观察，不执行
panic_confirmed → 抛压衰竭+反弹确认共振，可执行
```

### 7.2 第一段：恐慌程度计分（事件型因子，绝对阈值 — LLM 参考框架）

> 本段全部使用绝对或半绝对阈值，不做百分位化。以下阈值供 LLM 裁决时参考。

| 条件 | 类型 | 满足得分 |
|---|---|---|
| 指数单日跌幅 > 过去20日日均跌幅×2倍 | 事件型绝对阈值 | 30分 |
| VIX 单日涨幅 > 20% | 事件型绝对阈值 | 25分 |
| 下跌家数占比 > 75%（当日实时）| 半绝对阈值 | 25分 |
| 系统风险卡 1日 delta > +8 | 内部衍生指标 | 20分 |

```
panic_extreme_score = 各满足条件得分之和（满分100）

触发规则（4选3，改为计分制）：
  panic_extreme_score ≥ 55 → panic_watch = true（至少满足2-3条，但不要求全满足）
  panic_extreme_score ≥ 80 → 直接进入强恐慌确认，跳过 watch 阶段

设计原因：
  - 旧版"全部满足"会漏掉大量高赔率V反日（美股单日暴跌常常只有2-3条同时触发）
  - 计分制允许不同条件组合都能触发，更贴近实际市场踩踏场景
  - VIX 单日涨幅 > 20% 比"系统风险 delta > 8"信号量更强，计分制自然体现权重差异
```

### 7.3 第二段：抛压衰竭分（混合型因子）

| 因子 | 类型 | 计算方法 | 权重 |
|---|---|---|---|
| 尾盘回收率 | 慢变量百分位 | (close-intraday_low)/(intraday_high-intraday_low) → 百分位 | 30% |
| 次日成交量收缩 | 事件型绝对 | 今日量 < 昨日量×0.85 → 满足=50分，否则=0 | 25% |
| 领跌资产止跌 | 事件型绝对 | XLE/XLF/IWM 中≥2个今日跌幅 < 昨日×50% → 满足=50分 | 25% |
| 龙头不再创新低 | 半绝对 | RS>1.2股票中今日低点>昨日低点占比 > 60% | 20% |

### 7.4 第三段：反弹确认分（拆为当日尾盘确认 + 次日延续确认）

> 旧版确认因子过于依赖“次日”数据，会错过很多单日 V 反最有赔率的入场点。  
> V2.2 修订为两组确认：
>
> - `intraday_reversal_score`：服务当日尾盘 / 次日开盘初段的 early entry
> - `followthrough_confirmation_score`：服务次日延续确认后的加仓或升级

**A. 当日尾盘确认（intraday_reversal_score）**

| 因子 | 类型 | 计算方法 | 权重 |
|---|---|---|---|
| 尾盘站回前日中位价 | 事件型绝对 | close > (prev_high + prev_low) / 2 → 满足=40分 | 35% |
| 尾盘收在当日区间上半部 | 事件型绝对 | close > intraday_low + 0.5 × (intraday_high - intraday_low) → 满足=35分 | 30% |
| 高Beta资产尾盘同步修复 | 事件型绝对 | ARKK / 高Beta组合当日由负转正或收盘涨幅明显优于指数 → 满足=35分 | 20% |
| 短线卡分时不再恶化 | 内部衍生 | short_term_score intraday delta ≥ 0 或尾盘明显回升 → 满足=20分 | 15% |

**B. 次日延续确认（followthrough_confirmation_score）**

| 因子 | 类型 | 计算方法 | 权重 |
|---|---|---|---|
| 次日不大幅低开 | 事件型绝对 | 缺口 > -1.5% → 满足=40分，否则=0 | 35% |
| 次日继续站稳前日中位价 | 事件型绝对 | close > (prev_high + prev_low) / 2 → 满足=35分 | 30% |
| 高Beta资产次日继续修复 | 事件型绝对 | ARKK / 高Beta组合次日继续正收益 → 满足=35分 | 20% |
| 短线卡 delta 不再恶化 | 内部衍生 | short_term_score delta_1d ≥ 0 → 满足=20分 | 15% |

### 7.5 最终合成与状态机

```python
panic_reversal_score = (
    panic_extreme_score  * 0.40 +
    selling_exhaustion_score * 0.30 +
    max(intraday_reversal_score, followthrough_confirmation_score) * 0.30
)

# 状态机
if panic_extreme_score < 35:
    state = "无信号"
elif panic_extreme_score >= 80:
    state = "panic_confirmed"  # 强恐慌直接确认，允许 early entry
elif panic_extreme_score >= 35 and max(intraday_reversal_score, followthrough_confirmation_score) < 40:
    state = "panic_watch"      # 恐慌已到，等待确认，不开仓
elif panic_reversal_score >= 50:
    state = "panic_confirmed"  # 可执行
else:
    state = "panic_watch"
```

**状态机优先级说明**

- `panic_extreme_score >= 80` 为最高优先级，直接进入 `panic_confirmed`
- 若未达到强恐慌阈值，则先看是否进入 `panic_watch`
- `panic_watch` 升级为 `panic_confirmed` 的条件是：
  `panic_reversal_score >= 50`，或 `intraday_reversal_score >= 60`
- 这样可以保证：
  1. 强恐慌日不会被后续状态机误拦截
  2. 单日 V 反可以通过尾盘确认给出 early entry
  3. 次日延续确认仍可用于加仓和升级

### 7.6 分区与仓位

| 分区 | 分值 | 状态 | 动作 |
|---|---|---|---|
| 无信号 | 0-35 | — | 不操作 |
| 观察期 | 35-50 | panic_watch | 加入观察，不开仓 |
| 一级试错 | 50-65 | panic_confirmed | 轻仓 10%-20%，允许 early entry |
| 二级反弹 | 65-80 | panic_confirmed | 20%-35%（需次级确认共振）|
| 强反转窗口 | 80-100 | panic_confirmed | 35%-50%（仅反弹策略仓）|

**分区与状态统一规则**

- `panic_extreme_score < 35`：只能是“无信号”
- `panic_extreme_score >= 35` 且 `panic_reversal_score < 50`：归为 `panic_watch`
- `panic_reversal_score >= 50`：至少进入 `panic_confirmed`
- `panic_extreme_score >= 80`：即使合成分尚未到 50，也直接进入 `panic_confirmed`

这套规则保证分区表、状态机、前端展示三者完全一致，不再出现“UI 显示观察期，但引擎判无信号”的断层。

### 7.7 豁免确认延迟 + 独立仓位管理规则

```
时间规则：
  ✅ 触发即执行，不等主评分卡的3日降级确认
  ⚠️ 持有超过5个交易日自动触发警告（防止反弹仓熬成中线）

early entry 规则：
  若 state = panic_confirmed 且 intraday_reversal_score >= 60：
    → 允许当日尾盘或次日开盘初段建立 5%-10% 先手仓
  若次日 followthrough_confirmation_score >= 50：
    → 可把先手仓升级到一级试错或二级反弹仓位
  若次日未延续：
    → 先手仓按更紧止损退出，不得硬扛

止损规则：
  止损比趋势仓更紧：ATR × 1.0（趋势仓标准为 ATR × 1.5-2.0）
  持有2日后 followthrough_confirmation_score 仍 < 50 → 强制减仓50%

盈利兑现规则：
  达到 1R → 兑现50%仓位
  剩余50% → 止损移至成本线（消除本金风险）
  移动止损 → 跟踪持有，不设固定上限，让反弹自然展开

系统风险危机区覆盖：
  系统风险 > 80 时，即使 panic_reversal_score ≥ 80，仓位上限强制 ≤ 15%

仓位统计：
  反弹仓必须独立标记，不与趋势仓混同，禁止将反弹仓"熬成中线"
```

---

## 8. 完整输出结构（V2.2）

```json
{
  "timestamp": "2026-04-09T16:00:00-04:00",
  "data_freshness": "delayed_15min",

  "long_term_score": {
    "score": 39.5,
    "zone": "谨慎区",
    "delta_1d": -4.2,
    "delta_5d": -16.1,
    "slope_state": "加速恶化",
    "recommended_exposure": "20%-40%"
  },

  "short_term_score": {
    "score": 28.3,
    "zone": "弱势区",
    "delta_1d": -7.1,
    "delta_5d": -19.4,
    "slope_state": "加速恶化"
  },

  "system_risk_score": {
    "score": 74.1,
    "zone": "高压区",
    "liquidity_stress_score": 70.2,
    "risk_appetite_score": 78.0,
    "delta_1d": +10.3,
    "delta_5d": +26.5,
    "slope_state": "加速恶化",
    "pcr_percentile": 89.0,
    "pcr_absolute": 1.58,
    "pcr_panic_flag": true
  },

  "style_effectiveness": {
    "tactic_layer": {
      "trend_breakout":  { "score": 22, "valid": false, "delta_5d": -21 },
      "dip_buy":         { "score": 63, "valid": true,  "delta_5d": +10 },
      "oversold_bounce": { "score": 75, "valid": true,  "delta_5d": +28 },
      "top_tactic":   "超跌反弹",
      "avoid_tactic": "趋势突破"
    },
    "asset_layer": {
      "large_cap_tech":     { "score": 29, "preferred": false, "delta_5d": -18 },
      "small_cap_momentum": { "score": 16, "preferred": false, "delta_5d": -25 },
      "defensive":          { "score": 84, "preferred": true,  "delta_5d": +23 },
      "energy_cyclical":    { "score": 65, "preferred": true,  "delta_5d": +11 },
      "financials":         { "score": 41, "preferred": false, "delta_5d": -6  },
      "preferred_assets": ["防御板块", "能源/周期"],
      "avoid_assets":     ["小盘高弹性", "大盘科技"]
    }
  },

  "execution_card": {
    "regime_label": "红灯",
    "conflict_mode": "长弱短极差-净值保护",
    "total_exposure_range": "0%-20%",
    "new_position_allowed": false,
    "chase_breakout_allowed": false,
    "dip_buy_allowed": false,
    "overnight_allowed": false,
    "leverage_allowed": false,
    "single_position_cap": "5%",
    "daily_risk_budget": "0.25R",
    "tactic_preference": "无（红灯禁止进攻）",
    "preferred_assets": ["现金", "防御ETF对冲"],
    "signal_confirmation": {
      "current_regime_days": 1,
      "downgrade_unlock_in_days": 2,
      "note": "红灯第1日，需再维持2日后可评估降级"
    },
    "event_risk_flag": {
      "index_level": { "active": false },
      "stock_level": {
        "earnings_stocks": ["NVDA"],
        "rule": "NVDA 财报 T-1，单票上限减半，不影响regime"
      }
    }
  },

  "panic_reversal_score": {
    "score": 64.0,
    "zone": "一级试错",
    "state": "panic_confirmed",
    "panic_extreme_score": 80.0,
    "selling_exhaustion_score": 55.0,
    "reversal_confirmation_score": 42.0,
    "action": "恐慌充分+衰竭初现，确认尚弱，可10%-15%轻仓试探",
    "system_risk_override": "系统风险>70，反弹仓上限强制≤15%",
    "stop_loss": "ATR×1.0",
    "profit_rule": "达1R兑现50%，余仓移止损至成本线",
    "timeout_warning": false,
    "days_held": 0
  }
}
```

---

## 9. V2.1 → V2.2 改动对照表

| 模块 | V2.1 | V2.2 |
|---|---|---|
| **阈值策略** | 全部百分位，明确禁止绝对阈值 | 三类分治：慢变量百分位、事件型绝对阈值、混合型双路 |
| **panic_trigger** | 4条全满才触发，容易漏信号 | 计分制（满分100），≥55触发 watch，≥80直接确认 |
| **panic_watch** | 无此状态，只有触发/未触发 | 两级状态：watch（观察不执行）/ confirmed（可执行）|
| **风格卡** | 手法+资产混排，维度混乱 | 拆为两层：策略手法层 + 资产风格层，分别输出 |
| **冲突矩阵** | 缺"长线中性+短线强"场景 | 补充黄绿灯-Swing 场景，明确放开短线频率 |
| **确认延迟** | 统一3日降级，恐慌模块无豁免 | 恐慌模块完全豁免，以两级状态替代延迟安全门 |
| **事件风险** | 只有单一层，财报季混入regime | 指数级（影响regime）/ 个股级（只影响该股）严格分离 |
| **阶梯打分** | 部分因子仍为0/N二元打分 | 关键二元因子全部改为3-4档阶梯分，避免总分跳变 |
| **反弹盈利规则** | 只有止损规则，无盈利兑现 | 达1R兑现50%，余仓移止损至成本线 |
