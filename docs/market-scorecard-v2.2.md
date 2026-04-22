# 美股市场评分卡 V2.2

> 本版为 **可实现化修订版**。  
> 目标不是追求最理想的数据完备度，而是在当前约束下形成**稳定、可落地、可持续迭代**的市场监控评分框架。

当前约束：
- 本地结构化市场数据源：**yfinance**
- 评分方式：**每张评分卡单独请求 LLM**
- 信息不足时：**允许该评分卡对应的 LLM 请求主动联网搜索补充**
- 最终由执行卡汇总所有评分卡结论
- 系统结论以**刷新当刻可获取的数据**为准，不依赖“事件后 30 分钟观察”或“次日延续确认”之类未来信息

---

## 0. 实现方式说明

> **重要：本文档描述的因子、权重、阈值和分区表是 LLM 裁决时的参考知识框架，而非代码中硬编码实现的计算规则。**

### 0.1 目标架构

代码实现应采用 **“本地数据优先 + 单卡独立裁决 + 按需搜索补充”** 的架构，而非固定的规则引擎或统一 search stage。

完整流程如下：

1. **input_bundle**
   - 通过 yfinance 拉取本地结构化市场数据
   - 数据范围以指数、ETF、波动率与少量风险代理为主
   - 计算基础派生指标（收益率、均线、区间位置、ATR、相对强弱等）

2. **card_judgment**
   - 每张评分卡单独请求一次 LLM
   - 每次请求输入包括：
     - 该卡相关的本地结构化市场数据
     - 本文档定义的评分规则与决策框架
     - 当前已知的事实表
   - 若本地信息不足，允许该次 LLM 请求主动联网搜索补充

3. **execution_decision**
   - 长线、短线、系统风险、风格、事件风险、恐慌模块分别生成结构化结果
   - 执行卡综合所有评分卡输出最终 Regime 与动作建议

### 0.2 数据可得性边界

为避免文档要求超出当前实现条件，V2.2 将输入数据分为三层：

#### A. 核心必需数据（当前版本硬依赖）
必须可由 yfinance 获取或稳定派生：
- 宽基 ETF：`SPY, QQQ, IWM, DIA`
- 行业 ETF：`XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY, XLRE, XLC`
- 波动率代理：`^VIX`
- 信用风险代理：`LQD, JNK`
- 高 Beta proxy basket：`ARKK, IWM`
- 由以上数据派生的均线、ATR、区间位置、相对强弱、成交量变化、波动变化

#### B. 搜索增强数据（允许 LLM 按需联网补充）
可由 LLM 搜索补齐，但不要求具有统一历史序列：
- FOMC / CPI / PCE / 非农等宏观事件日历
- 财报日历与重点个股事件
- 政策 / 地缘 / 监管新闻
- 风险情绪与重大市场叙事
- 明确的突发事件说明

#### C. 可选增强数据（当前版本不作为硬依赖）
这类数据若未来接入专门数据源可增强，但当前版本默认不要求：
- 交易所级 breadth 原始数据
- A/D 线、新高新低净差等市场内部统计
- 股票级 RS 横截面
- 股票样本级突破成功率与赚钱效应统计
- PCR 百分位 / 市场级 Put-Call Ratio 双路径

### 0.3 本文档的定位

- 下文定义的是 LLM 裁决时应参考的**领域知识框架与标准输出结构**
- 当某类理想数据当前不可得时，LLM 应优先使用 ETF / 指数 / 波动率 proxy，而不是编造事实
- 若本地数据不足且联网搜索也无法稳定确认，LLM 应在 risks / confidence 中明确说明不确定性
- Prompt 设计应将本文档的核心规则编入 system instructions 或结构化 fact sheet 上下文

### 0.4 搜索治理规则

为避免搜索增强污染本地结构化判断，当前版本统一采用以下规则：

1. **本地结构化数据优先**：搜索结果不能覆盖本地量化指标，只能补充解释、事件与背景信息。
2. **搜索只补事件与叙事**：搜索增强的主要对象是宏观日历、财报事件、政策/地缘、风险情绪和突发新闻，而不是替代本地价格/波动率/成交量数据。
3. **搜索结论必须可溯源**：搜索结果应附带 evidence / source summary；若多来源冲突，优先官方日历、交易所/公司公告和主流财经媒体。

### 0.5 当前实现的额外特性（文档外）

以下特性可实现，但不属于评分卡逻辑本身：
- Prompt 审计追踪
- 运行阶段持久化与恢复
- 并发限制与超时保护
- 搜索结果与事实表的证据索引

---

## 1. 全局数据标准化原则（修订版）

### 1.1 两类因子，两种阈值策略

在当前数据约束下，V2.2 采用更朴素、更稳定的两类因子划分：

| 因子类型 | 特征 | 适合方法 | 典型例子 |
|---|---|---|---|
| **慢变量 / 水位型** | 反映结构性压力或环境背景，缓慢漂移 | 252日滚动百分位 | VIX 水位、LQD/JNK 风险代理水位、ETF 相对强弱 |
| **事件型 / 速度型** | 反映单次刷新时点的冲击强度，离散触发 | 绝对阈值或半绝对阈值 | VIX 单次刷新涨幅、指数阶段性跌幅、隔夜缺口幅度 |

```python
# 慢变量：252日百分位标准化
def to_percentile_score(series: pd.Series, current_value: float) -> float:
    return percentileofscore(series.dropna(), current_value)

# 事件型：直接用绝对阈值
def is_vix_spike(vix_1d_change: float) -> bool:
    return vix_1d_change > 0.20
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

### 1.3 Proxy 使用原则

当前版本统一采用以下 proxy 原则：

1. **breadth 用 ETF proxy 表达，不要求交易所级原始 breadth feed**
2. **行业赚钱效应与风格偏好以行业 ETF / 风格 ETF 表达**
3. **股票横截面统计不足时，用指数 / ETF / 风格相对强弱替代**
4. **不使用 PCR 百分位或市场级 Put-Call Ratio 双路径作为核心硬依赖**
5. **panic 模块以指数 / ETF / 波动率为主，宽市场横截面数据只作未来增强项**

---

## 2. 长线环境卡

### 2.1 因子量化映射（LLM 参考框架）

> 以下因子和权重供 LLM 裁决时参考，非代码硬编码计算。

**趋势结构（权重 40%）**

| 因子 | 计算方法 | 评分规则 |
|---|---|---|
| SPY 与 200 日均线关系 | (close - MA200) / MA200 | 阶梯分：偏离 >+3% → 25分；0~+3% → 18分；-2%~0 → 10分；<-2% → 0分 |
| SPY 50 日均线斜率 | MA50_today - MA50_20d_ago | 252日百分位 → 0-25分 |
| SPY 相对 3 月区间位置 | (close - 3m_low) / (3m_high - 3m_low) | 连续分 0-25分 |
| QQQ 与 SPY 趋势同步性 | 两者 20日收益率方向 | 同向上升 → 25分；分歧 → 12分；同降 → 0分 |

**广度修复（权重 25%）— ETF proxy 版**

| 因子 | 计算方法 | 评分规则 |
|---|---|---|
| 核心风险资产扩散度 | `SPY, QQQ, IWM, DIA` 中站上 MA50 与 MA200 的资产数量 | 0-100 连续映射 |
| 行业 ETF 扩散度 | 行业 ETF universe 中，5日收益率为正或站上 MA50 的数量占比 | 252日百分位 → 0-40分 |
| 进攻 / 防御比强弱 | `QQQ, IWM` 相对 `XLU, XLP, XLV` 的 10日表现 | 进攻显著占优 → 高分；防御显著占优 → 低分 |

**龙头确认（权重 15%）— ETF / 行业 proxy 版**

| 因子 | 计算方法 | 评分规则 |
|---|---|---|
| 大盘科技领导性 | QQQ vs SPY 10日相对动量 | 连续分 |
| 小盘确认度 | IWM vs SPY 10日相对动量 | 连续分 |
| 周期板块参与度 | XLE / XLB / XLF 相对 SPY 的 10日动量均值 | 周期参与越广，高分越高 |

**波动健康度（权重 20%）**

| 因子 | 计算方法 | 评分规则 |
|---|---|---|
| VIX 水位 | 252日百分位，反向 | 100 - VIX_pct |
| VIX 变化趋势 | VIX 5日变化与 20日均值偏离 | 快速抬升降分，回落加分 |
| 风险信用代理 | LQD / JNK 相对强弱或 JNK 回撤压力 | 信用风险放大则降分 |

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

> 当前版本的短线卡以 ETF / 行业 proxy 为主，不依赖股票级样本统计。

**热点延续性（权重 30%）**

| 因子 | 计算方法 |
|---|---|
| 行业 ETF 5日动量 vs 20日动量 | 5日超额动量 >0 的行业数占比 → 252日百分位 |
| 强势行业延续率 | 领先行业 ETF 在最近连续刷新中的相对强势是否保持 |
| 风格切换稳定度 | `QQQ, IWM, XLE, XLF` 等风格 ETF 最近 3-5 日强弱顺序是否稳定 |

**突破友好度（权重 25%）— ETF proxy 版**

| 因子 | 计算方法 |
|---|---|
| ETF 突破持续率 | 主要 ETF 突破近20日高点后的近期延续表现 |
| ETF 放量守住率 | 突破日放量后是否守住突破位 |

**板块赚钱效应（权重 25%）— 行业 proxy 版**

| 因子 | 计算方法 |
|---|---|
| 行业轮动连续性 | 近期领先行业 ETF 的相对强势是否延续 |
| 高 Beta / 周期风格参与度 | `ARKK, IWM, XLE, XLF` 是否同步改善 |
| 防御板块压制程度 | `XLU, XLP, XLV` 是否持续跑赢风险资产 |

**波动友好度（权重 20%）**

| 因子 | 计算方法 |
|---|---|
| SPY ATR% | 252日百分位，中位数得分最高 |
| 隔夜缺口质量 | 近5日正向缺口占比与缺口后延续情况 |
| VIX 1日 / 5日变化 | 波动率快速抬升则降分 |

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

> 当前版本移除 PCR 百分位 / 市场级 Put-Call Ratio 双路径，系统风险主要由波动率、信用代理、防御偏好与跨资产相对强弱构成。

**流动性压力分（权重 50%）**

| 因子 | 类型 | 计算方法 | 权重 |
|---|---|---|---|
| VIX 水位 | 慢变量 | 252日百分位 | 35% |
| VIX 阶段性抬升速度 | 事件型 | 5日变化 / 20日基准 | 20% |
| IG 风险代理 | 慢变量 | LQD 相对 SPY / 自身趋势位置 | 20% |
| HY 风险代理 | 慢变量 | JNK 相对 LQD / SPY 表现 | 25% |

**风险偏好分（权重 50%）**

| 因子 | 类型 | 计算方法 | 权重 |
|---|---|---|---|
| IWM/SPY 5日相对表现 | 慢变量 | 252日百分位（低=防御） | 30% |
| XLU/SPY 5日相对表现 | 慢变量 | 252日百分位（高=避险） | 25% |
| ARKK/SPY 5日相对表现 | 慢变量 | 高 Beta 风险偏好代理 | 20% |
| 跨资产同步下跌压力 | 慢变量 | SPY / QQQ / IWM / JNK 近5日共同走弱程度 | 25% |

### 4.2 事件型风险触发原则

```
系统风险卡中的事件型风险主要来自：
  - VIX 单次刷新 / 5日快速抬升
  - 风险资产与高收益债同步走弱
  - 宏观事件或地缘风险搜索结果明显恶化

这些信号可：
  - 直接抬升 system_risk_score
  - 作为 execution card 收紧权限的依据
  - 为 panic 模块提供背景风险信息
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

> V2.2 保留“两层结构”，但当前版本全部基于 ETF / 行业 proxy，不要求股票横截面统计。

### 5.1 第一层：策略手法有效性

**回答问题：用什么方式进场？**

| 手法 | 计算方法 | 数据 |
|---|---|---|
| **趋势突破** | `SPY, QQQ, IWM` 与主要行业 ETF 突破近20日高点后的近期延续表现 | 指数 / ETF 日线 |
| **回调低吸** | 主要 ETF 回踩 5-10 日均线或短期低点后的近期修复表现 | 指数 / ETF 日线 |
| **超跌反弹** | `SPY, QQQ, IWM, ARKK` 等高 Beta proxy basket 在短期急跌后的修复强度 | 指数 / ETF 日线 |

输出：`top_tactic`、`avoid_tactic`

### 5.2 第二层：资产风格偏好

**回答问题：做哪个方向？**

| 风格 | 计算方法 | 数据 |
|---|---|---|
| **大盘科技** | QQQ vs SPY 10日相对动量 | ETF 日线 |
| **小盘高弹性** | IWM vs SPY 10日相对动量 | ETF 日线 |
| **防御板块** | (XLU+XLV+XLP)/3 vs SPY 10日相对 | ETF 日线 |
| **能源/周期** | (XLE+XLB)/2 vs SPY 10日相对 | ETF 日线 |
| **金融** | XLF vs SPY 10日相对 | ETF 日线 |

输出：`preferred_assets`、`avoid_assets`

### 5.3 两层组合使用示例

```
手法层：趋势突破差，回调低吸好
资产层：防御板块强，小盘弱

→ 执行卡读取：等回调后低吸防御板块 ETF，不追涨，不碰小盘
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
| 中性（45-65）| 强（≥60）| 低（≤35）| 🟢 黄绿灯-Swing | 允许积极 swing，不建趋势重仓 |
| 中性（45-65）| 中性（45-55）| 正常（≤50）| 🟡 黄灯 | 低频操作，低吸+确认突破，不提高频率 |
| 中性（45-65）| 弱（<45）| 任意 | 🟠 橙灯 | 控仓，防守为主 |
| 弱（<45）| 强（≥55）| 低（≤35）| 🟡 黄灯-短线 | 只允许短线博弈仓，不建趋势仓 |
| 弱（<45）| 弱（<45）| 任意 | 🔴 红灯 | 净值保护，禁一切新开仓 |
| 任意 | 任意 | 高（>70）| 🔴 红灯 | 危机模式，只保对冲，杠杆全清 |

### 6.2 风险收紧 / 风险放宽机制（含恐慌模块豁免）

```
主评分卡（长线/短线/系统风险）：
  风险收紧（risk tightening）：触发1次即生效 → 风险保护优先
  风险放宽（risk loosening）：需连续3次刷新保持后才放宽 → 防假突破

恐慌反转模块：完全豁免上述规则
  → 触发即执行，快进快出，不等任何延迟确认
  → 代替延迟机制的是：panic_watch / panic_confirmed 两级状态
```

### 6.3 事件风险层：指数级 vs 个股级分离

**指数级事件（影响整体 regime）**

| 事件 | 即时规则 |
|---|---|
| FOMC 决议日 | 刷新时若事件临近或正在发生，可直接收紧新开仓与隔夜权限 |
| CPI / PCE 公布 | 刷新时若事件临近或正在发生，可直接禁追高或收紧仓位 |
| 非农数据 | 同上 |
| 地缘危机爆发（突发） | 当次刷新若搜索证据明确，可立即进入更保守执行模式 |

**个股级事件（只影响该股，不污染 regime）**

| 事件 | 规则 |
|---|---|
| 个股财报日（T-1 / T） | 财报前1日该股单票上限减半；财报当日禁追高 |
| 个股重大公告 | 同上 |
| 财报季密集期 | 在个股层面加财报标记，不影响指数 regime label |

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
    "current_regime_observations": 3,
    "risk_loosening_unlock_in_observations": 0,
    "note": "已连续3次刷新保持，可正常评估风险放宽"
  },
  "event_risk_flag": { ... }
}
```

---

## 7. 恐慌反转捕捉模块（重构版）

> 当前版本的 panic 模块以 **指数 / ETF / 波动率** 为主，不依赖市场级 breadth feed、龙头股横截面或 PCR 双路径。

### 7.1 两级状态设计

```
panic_watch     → 恐慌已开始，进入观察，不执行
panic_confirmed → 抛压衰竭+反弹确认共振，可执行
```

### 7.2 第一段：恐慌程度计分（事件型因子，绝对阈值）

| 条件 | 类型 | 满足得分 |
|---|---|---|
| `SPY / QQQ / IWM / DIA` 任一指数型代理单次刷新跌幅 > 过去20次均值 × 2 | 事件型绝对阈值 | 30分 |
| VIX 单次刷新涨幅 > 20% | 事件型绝对阈值 | 25分 |
| 高 Beta proxy basket（`ARKK / IWM`）显著失速 | 事件型绝对阈值 | 20分 |
| 系统风险卡 1次刷新 delta > +8 | 内部衍生指标 | 25分 |

```python
panic_extreme_score = 各满足条件得分之和

if panic_extreme_score >= 55:
    panic_watch = True
if panic_extreme_score >= 80:
    state = "panic_confirmed"
```

### 7.3 第二段：抛压衰竭分

| 因子 | 类型 | 计算方法 | 权重 |
|---|---|---|---|
| 尾盘回收率 | 事件型恢复指标 | (close - low) / (high - low) | 35% |
| 成交量收缩迹象 | 事件型绝对 | 当前成交量强度 < 最近恐慌刷新时段的 0.85 倍，可视为成交量收缩 | 20% |
| 领跌资产止跌 | 事件型绝对 | `IWM / ARKK / XLE / XLF` 中至少两项跌幅显著收敛 | 25% |
| VIX 回落迹象 | 事件型绝对 | VIX 明显脱离刷新时高位 | 20% |

### 7.4 第三段：即时反弹确认分

> 当前版本不依赖未来时点数据。  
> 反弹确认仅基于**刷新当刻可见的指数 / ETF / 波动率行为**。

| 因子 | 类型 | 计算方法 | 权重 |
|---|---|---|---|
| 站回前一参考中位价 | 事件型绝对 | close > (prev_high + prev_low) / 2 | 35% |
| 收在当前区间上半部 | 事件型绝对 | close > low + 0.5 × (high - low) | 30% |
| 高 Beta proxy basket 同步修复 | 事件型绝对 | `ARKK / IWM` 表现明显优于刷新时低点 | 20% |
| 短线环境不再恶化 | 内部衍生 | short_term_score 明显止跌或回升 | 15% |

### 7.5 最终合成与状态机

```python
panic_reversal_score = (
    panic_extreme_score * 0.40 +
    selling_exhaustion_score * 0.30 +
    intraday_reversal_score * 0.30
)

if panic_extreme_score < 35:
    state = "无信号"
elif panic_extreme_score >= 80:
    state = "panic_confirmed"
elif panic_extreme_score >= 35 and intraday_reversal_score < 40:
    state = "panic_watch"
elif panic_reversal_score >= 50:
    state = "panic_confirmed"
else:
    state = "panic_watch"
```

### 7.6 分区与仓位

| 分区 | 分值 | 状态 | 动作 |
|---|---|---|---|
| 无信号 | 0-35 | — | 不操作 |
| 观察期 | 35-50 | panic_watch | 加入观察，不开仓 |
| 一级试错 | 50-65 | panic_confirmed | 轻仓 10%-20%，允许即时试探 |
| 二级反弹 | 65-80 | panic_confirmed | 20%-35% |
| 强反转窗口 | 80-100 | panic_confirmed | 35%-50%（仅反弹策略仓） |

### 7.7 豁免确认延迟 + 独立仓位管理规则

```
时间规则：
  ✅ 触发即执行，不等主评分卡的3次风险放宽确认
  ⚠️ 持有超过5次刷新周期自动触发警告

即时试探规则：
  若 state = panic_confirmed 且 intraday_reversal_score >= 60：
    → 允许刷新当刻建立 5%-10% 先手仓
  若后续刷新仍保持确认：
    → 可把先手仓升级到一级试错或二级反弹仓位
  若后续刷新失去确认：
    → 先手仓按更紧止损退出，不得硬扛

止损规则：
  止损比趋势仓更紧：ATR × 1.0
  若后续两次刷新后 panic 确认明显减弱 → 强制减仓50%

盈利兑现规则：
  达到 1R → 兑现50%仓位
  剩余50% → 止损移至成本线

系统风险危机区覆盖：
  系统风险 > 80 时，即使 panic_reversal_score ≥ 80，仓位上限强制 ≤ 15%
```

### 7.8 输出结构

```json
"panic_reversal_score": {
  "score": 64.0,
  "zone": "一级试错",
  "state": "panic_confirmed",
  "panic_extreme_score": 80.0,
  "selling_exhaustion_score": 55.0,
  "intraday_reversal_score": 42.0,
  "action": "恐慌充分+衰竭初现，确认尚弱，可10%-15%轻仓试探",
  "system_risk_override": "系统风险>70，反弹仓上限强制≤15%",
  "stop_loss": "ATR×1.0",
  "profit_rule": "达1R兑现50%，余仓移止损至成本线",
  "timeout_warning": false,
  "refreshes_held": 0
}
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
    "delta_1d": 10.3,
    "delta_5d": 26.5,
    "slope_state": "加速恶化"
  },

  "style_effectiveness": {
    "tactic_layer": {
      "trend_breakout":  { "score": 22, "valid": false, "delta_5d": -21 },
      "dip_buy":         { "score": 63, "valid": true,  "delta_5d": 10 },
      "oversold_bounce": { "score": 75, "valid": true,  "delta_5d": 28 },
      "top_tactic": "超跌反弹",
      "avoid_tactic": "趋势突破"
    },
    "asset_layer": {
      "large_cap_tech":     { "score": 29, "preferred": false, "delta_5d": -18 },
      "small_cap_momentum": { "score": 16, "preferred": false, "delta_5d": -25 },
      "defensive":          { "score": 84, "preferred": true,  "delta_5d": 23 },
      "energy_cyclical":    { "score": 65, "preferred": true,  "delta_5d": 11 },
      "financials":         { "score": 41, "preferred": false, "delta_5d": -6 },
      "preferred_assets": ["防御板块", "能源/周期"],
      "avoid_assets": ["小盘高弹性", "大盘科技"]
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
      "current_regime_observations": 1,
      "risk_loosening_unlock_in_observations": 2,
      "note": "当前仍处于风险收紧状态，需再连续2次刷新保持后才可评估放宽"
    },
    "event_risk_flag": {
      "index_level": { "active": false },
      "stock_level": {
        "earnings_stocks": ["NVDA"],
        "rule": "NVDA 财报 T-1，单票上限减半，不影响 regime"
      }
    }
  },

  "panic_reversal_score": {
    "score": 64.0,
    "zone": "一级试错",
    "state": "panic_confirmed",
    "panic_extreme_score": 80.0,
    "selling_exhaustion_score": 55.0,
    "intraday_reversal_score": 42.0,
    "action": "恐慌充分+衰竭初现，确认尚弱，可10%-15%轻仓试探",
    "system_risk_override": "系统风险>70，反弹仓上限强制≤15%",
    "stop_loss": "ATR×1.0",
    "profit_rule": "达1R兑现50%，余仓移止损至成本线",
    "timeout_warning": false,
    "refreshes_held": 0
  }
}
```