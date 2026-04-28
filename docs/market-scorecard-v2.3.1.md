# 美股市场评分卡 V2.3.1

> 本版为 **可回测、可审计、可实现化修订版**。
> 目标不是追求最理想的数据完备度，而是在当前约束下形成稳定、可落地、可持续校准的市场监控评分协议。

当前约束：
- 本地结构化市场数据源：**yfinance**
- 评分方式：**每张评分卡单独请求 LLM**
- 信息不足时：**允许评分流程按需联网搜索补充事件与叙事，但搜索结果必须先规范化为统一的 `event_fact_sheet`，再进入评分卡与执行卡**
- 最终由执行卡汇总所有评分卡结论
- 系统结论以**刷新当刻可获取的数据**为准，不依赖“事件后 30 分钟观察”或“次日延续确认”之类未来信息

V2.3.1 修复重点：
- 将“LLM 自由裁决”收紧为“确定性因子计算 + LLM 解释、冲突处理和置信度调整”
- 统一所有分数方向与因子审计字段
- 明确 yfinance 日线 / 盘中数据边界
- 将搜索治理升级为结构化 `event_fact_sheet`
- 重写系统风险与 panic 状态机，避免“恐慌充分”被误判为“反转确认”
- 扩展完整输出结构，支持后续回测、复盘和 prompt 审计
- 修正数据新鲜度、百分比单位、执行阈值和 panic 分区的歧义

---

## 0. 实现方式说明

### 0.1 目标架构

代码实现应采用 **“本地数据优先 + 确定性因子计算 + 统一事件事实表 + 单卡独立 LLM 裁决”** 的架构。

完整流程如下：

1. **input_bundle**
   - 通过 yfinance 拉取本地结构化市场数据
   - 数据范围以指数、ETF、波动率与少量风险代理为主
   - 计算基础派生指标：收益率、均线、区间位置、ATR、相对强弱、成交量变化、波动变化
   - 记录 `input_data_status` 与 `missing_data`

2. **deterministic_factor_layer**
   - 由代码 / 规则层确定性计算：
     - `factor_values`
     - `factor_scores`
     - `factor_breakdown`
     - `missing_flags`
   - 因子计算应尽量可复现、可回测、可单元测试
   - LLM 不应替代本地价格、成交量、波动率、均线、百分位等结构化计算

3. **event_fact_sheet**
   - 对宏观日历、财报日历、政策/地缘、监管新闻和突发事件做按需搜索
   - 搜索可发生在单独预搜索阶段，也可由某张评分卡触发
   - 无论搜索由谁触发，结果必须写入统一的 `event_fact_sheet`
   - 同一刷新周期内，后续评分卡与执行卡只能读取统一事实表，不得各自保留互相矛盾的私有搜索结论
   - 搜索事实不能覆盖本地价格、成交量、波动率、均线、百分位等结构化指标

4. **card_judgment**
   - 每张评分卡单独请求一次 LLM
   - 每次请求输入包括：
     - 该卡相关的本地结构化市场数据
     - 确定性因子计算结果
     - 本文档定义的评分方向、冲突规则与输出结构
     - 当前已知的 `event_fact_sheet`
   - LLM 负责：
     - 解释分数
     - 标注风险与不确定性
     - 对事件、叙事、宏观日历提出补充搜索需求，或消费已经规范化的搜索事实
     - 在规则允许范围内调整置信度与执行语气
   - LLM 不得编造缺失市场数据。若数据不足，必须在 `missing_data`、`risks`、`confidence` 中说明。

5. **execution_decision**
   - 长线、短线、系统风险、风格、事件风险、恐慌模块分别生成结构化结果
   - 执行卡按固定优先级综合所有评分卡输出最终 Regime 与动作建议

### 0.2 数据可得性边界

为避免文档要求超出当前实现条件，V2.3.1 将输入数据分为三层：

#### A. 核心必需数据（V2.3.1 硬依赖）

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

#### C. 可选增强数据（V2.3.1 不作为硬依赖）

这类数据若未来接入专门数据源可增强，但 V2.3.1 默认不要求：
- 交易所级 breadth 原始数据
- A/D 线、新高新低净差等市场内部统计
- 股票级 RS 横截面
- 股票样本级突破成功率与赚钱效应统计
- PCR 百分位 / 市场级 Put-Call Ratio 双路径
- 增强跨资产代理：`HYG, TLT, IEF, SHY, ^TNX, UUP, GLD`

### 0.3 本文档的定位

- 本文档定义的是市场评分卡的**领域知识、评分方向、审计结构与输出协议**
- 因子值与基础分数应优先由确定性代码计算，不应交给 LLM 自由生成
- LLM 可以对事件、叙事和冲突状态做解释，但不得覆盖本地结构化指标
- 当某类理想数据当前不可得时，系统应优先使用 ETF / 指数 / 波动率 proxy，而不是编造事实
- 若本地数据不足且联网搜索也无法稳定确认，LLM 应在 `missing_data`、`risks`、`confidence` 中明确说明不确定性
- Prompt 设计应将本文档的核心规则编入 system instructions 或结构化 fact sheet 上下文

### 0.3.1 LLM 裁决边界

为保证可回测和可审计，LLM 与规则层的职责必须明确分离：

| 项目 | 责任方 | 规则 |
|---|---|---|
| 原始行情、成交量、波动率、均线、百分位 | 确定性代码 | LLM 不得生成、补写或覆盖 |
| `factor_breakdown.score` | 确定性代码 | LLM 不得直接改写 |
| 卡片 `score` | 确定性代码为主 | 默认等于确定性合成分；若引入事件冲击，必须通过结构化 `event_triggers` 或 `score_adjustment` 审计字段体现 |
| `confidence`、`risks`、`evidence`、解释文字 | LLM | 可根据数据缺口、事件冲突和叙事不确定性调整 |
| 执行权限收紧 | 执行卡规则层 + LLM 解释 | 只能更保守，不能因为叙事乐观而越过系统风险 override |

若某张评分卡允许 LLM 对 `score` 做事件型调整，必须满足：
- 调整来源必须来自 `event_fact_sheet` 或本地确定性触发器。
- 输出必须包含 `score_adjustment`，说明方向、幅度、依据、过期时间和置信度。
- 默认单次 LLM 事件调整幅度不超过 `±5` 分；超过时必须由规则层白名单触发，例如危机级地缘事件或交易所异常。
- 回测时必须能同时复现“未调整分数”和“调整后分数”。

### 0.4 搜索治理规则：`event_fact_sheet`

搜索增强必须输出结构化事实表。搜索结果不能覆盖本地量化指标，只能补充解释、事件与背景信息。

每条搜索事实必须包含：

```json
{
  "event_id": "2026-04-29-fomc-decision",
  "event": "FOMC decision",
  "scope": "index_level",
  "time_window": "today_after_close",
  "severity": "high",
  "source_type": "official_calendar",
  "source_name": "Federal Reserve",
  "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
  "source_summary": "美联储议息结果将在收盘后公布，可能影响隔夜风险。",
  "observed_at": "2026-04-29T10:15:00-04:00",
  "confidence": 0.92,
  "expires_at": "2026-04-29T20:00:00-04:00"
}
```

治理规则：
1. **本地结构化数据优先**：搜索结果不能覆盖本地价格、波动率、成交量和衍生指标。
2. **搜索只补事件与叙事**：宏观日历、财报事件、政策/地缘、风险情绪和突发新闻可搜索补充。
3. **搜索结论必须可溯源**：优先官方日历、交易所/公司公告和主流财经媒体；事实表必须保留 `source_name` 与 `source_url`，无法提供链接时必须在 `risks` 中说明。
4. **搜索事实必须过期**：事件类事实必须写入 `expires_at`，避免旧事件污染后续刷新。
5. **冲突来源降置信度**：多来源冲突时不强行裁决事实，应降低 `confidence` 并写入 `risks`。
6. **同周期事实去重**：同一事件在同一刷新周期内只能保留一个主事实；多来源证据应合并到同一 `event_id` 下，而不是生成多个互相竞争的事件。
7. **执行卡只消费事实表**：执行卡不得重新搜索或私自修改事件事实，只能基于统一 `event_fact_sheet` 做权限收紧、置信度调整和风险说明。

### 0.5 当前实现的额外特性（文档外）

以下特性可实现，但不属于评分卡逻辑本身：
- Prompt 审计追踪
- 运行阶段持久化与恢复
- 并发限制与超时保护
- 搜索结果与事实表的证据索引

---

## 1. 全局数据标准化原则

### 1.1 分数方向

所有评分卡必须显式声明分数方向：

| 模块 | 分数方向 |
|---|---|
| `long_term_score` | 越高代表长线环境越友好 |
| `short_term_score` | 越高代表短线交易环境越友好 |
| `system_risk_score` | 越高代表系统风险越高、越危险 |
| `style_effectiveness` | 越高代表对应手法或资产风格越有效 |
| `panic_extreme_score` | 越高代表恐慌越强，不等于反转确认 |
| `panic_reversal_score` | 越高代表恐慌反弹机会越强，但仍需确认条件 |

### 1.2 数据模式：`data_mode`

yfinance 数据必须区分日线与盘中语义：

| data_mode | 含义 | 可使用指标 | 禁止误用 |
|---|---|---|---|
| `daily` | 仅使用日线 OHLCV | 日收益、均线、日 ATR、日区间位置、日成交量 | 不得声称“刷新时高位/低位”“尾盘回收率”“盘中脱离高位” |
| `intraday_delayed` | 使用延迟盘中数据 | 刷新时 high/low、盘中区间位置、盘中 VIX 变化 | 必须注明 interval、延迟和是否含盘前盘后 |
| `intraday_realtime` | 使用实时盘中数据 | 同上，并可用于更即时的 panic 判定 | 必须注明数据源和稳定性限制 |

`data_freshness` 用于说明数据新鲜度，例如 `previous_trading_day`、`daily_final`、`daily_partial`、`delayed_15min`、`realtime`；它不能单独替代 `data_mode`。

推荐组合：
- `data_mode = daily` 且只使用已收盘日线：`data_freshness = previous_trading_day` 或 `daily_final`。
- `data_mode = daily` 且 yfinance 返回当日未收盘日线：`data_freshness = daily_partial`，且必须避免盘中语言。
- `data_mode = intraday_delayed`：`data_freshness` 可为 `delayed_15min` 等，并必须记录 `interval`。
- `data_mode = intraday_realtime`：`data_freshness = realtime`，并必须记录实时数据源。

### 1.3 区间端点规则

所有分区、仓位区间和 Regime 阈值默认使用**左闭右开**区间，最后一个区间包含 100：

```text
[0, 35)   表示 score >= 0  且 score < 35
[35, 50)  表示 score >= 35 且 score < 50
[80, 100] 表示 score >= 80 且 score <= 100
```

执行矩阵中的文字标签也必须遵守同一规则。例如：
- `强（[65,80)）` 不包含 80，80 进入 `强趋势（[80,100]）`。
- `中性（[45,65)）` 不包含 65，65 进入 `强（[65,80)）`。
- `高压（[70,80)）` 不包含 80，80 进入 `危机（[80,100]）`。

### 1.4 两类因子，两种阈值策略

除非字段名明确写作 `*_ratio`，本文所有收益率、涨跌幅、ATR%、距离均线百分比、区间位置和变化幅度默认采用**百分数单位**，即 `20%` 记为 `20.0`，不是 `0.20`。若实现层使用小数单位，必须在 `factor_breakdown.raw_value_unit` 中显式标记并在归一化前转换。

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
    # vix_1d_change 使用百分数单位，20% 记为 20.0。
    return vix_1d_change > 20.0
```

### 1.5 变化量与斜率状态

```python
delta_1d = score_today - score_yesterday
delta_5d = score_today - score_5d_ago

def benefit_score_slope_state(delta_1d, delta_5d):
    """用于 long_term_score、short_term_score、style_effectiveness 等越高越好的分数。"""
    if delta_1d > 3  and delta_5d > 8:   return "加速改善"
    if delta_1d > 0  and delta_5d > 3:   return "缓慢改善"
    if abs(delta_1d) <= 2:               return "钝化震荡"
    if delta_1d < 0  and delta_5d < -3:  return "缓慢恶化"
    if delta_1d < -3 and delta_5d < -8:  return "加速恶化"
    return "震荡"

def risk_score_slope_state(delta_1d, delta_5d):
    """用于 system_risk_score 等越高越危险的分数。"""
    if delta_1d > 3  and delta_5d > 8:   return "风险加速上升"
    if delta_1d > 0  and delta_5d > 3:   return "风险缓慢上升"
    if abs(delta_1d) <= 2:               return "风险钝化震荡"
    if delta_1d < 0  and delta_5d < -3:  return "风险缓慢回落"
    if delta_1d < -3 and delta_5d < -8:  return "风险加速回落"
    return "风险震荡"
```

禁止对 `system_risk_score` 复用 `benefit_score_slope_state`。系统风险分数上升必须输出“风险上升”，不能输出“改善”。

### 1.6 因子审计字段：`factor_breakdown`

每张评分卡必须能解释核心因子的来源和方向。建议结构如下：

```json
{
  "factor": "vix_level",
  "raw_value": 18.6,
  "raw_value_unit": "index_points",
  "percentile": 72.0,
  "polarity": "higher_is_riskier",
  "score": 72.0,
  "weight": 0.35,
  "reason": "VIX 位于过去252日较高分位，系统风险上升。",
  "data_status": "available"
}
```

字段约定：
- `raw_value`：原始值或派生指标值
- `raw_value_unit`：原始值单位，例如 `pct`、`ratio`、`index_points`、`usd`、`count`；百分数单位用 `pct`
- `percentile`：如适用，使用 252 日滚动百分位
- `polarity`：`higher_is_better`、`higher_is_riskier`、`middle_is_better`、`lower_is_better`
- `score`：归一到 0-100 后的因子分
- `weight`：该因子在当前卡中的参考权重
- `reason`：面向投研解释的简短说明
- `data_status`：`available`、`missing`、`proxy_used`、`search_only`

若卡片 `score` 不等于确定性合成分，必须额外输出：

```json
{
  "deterministic_score": 68.0,
  "score": 72.0,
  "score_adjustment": {
    "value": 4.0,
    "direction": "risk_up",
    "reason": "CPI 次日盘前公布，隔夜事件风险上升。",
    "source_event_ids": ["2026-04-10-cpi-release"],
    "confidence": 0.84,
    "expires_at": "2026-04-10T10:30:00-04:00"
  }
}
```

若没有调整，`deterministic_score` 应等于 `score`，`score_adjustment` 可为 `null`。

### 1.7 Proxy 使用原则

V2.3.1 统一采用以下 proxy 原则：

1. breadth 用 ETF proxy 表达，不要求交易所级原始 breadth feed。
2. 行业赚钱效应与风格偏好以行业 ETF / 风格 ETF 表达。
3. 股票横截面统计不足时，用指数 / ETF / 风格相对强弱替代。
4. 不使用 PCR 百分位或市场级 Put-Call Ratio 双路径作为核心硬依赖。
5. panic 模块以指数 / ETF / 波动率为主，宽市场横截面数据只作未来增强项。

---

## 2. 长线环境卡

### 2.1 因子量化映射

长线环境分越高，代表中期趋势、广度、风险偏好和波动状态越适合持有风险资产。

**趋势结构（权重 40%）**

| 因子 | 计算方法 | 评分方向 |
|---|---|---|
| SPY 与 200 日均线关系 | `(close - MA200) / MA200` | 越高越友好 |
| SPY 50 日均线斜率 | `MA50_today - MA50_20d_ago` | 252日百分位，越高越友好 |
| SPY 相对 3 月区间位置 | `(close - 3m_low) / (3m_high - 3m_low)` | 越高越友好，但极端过热需由 LLM 风险提示 |
| QQQ 与 SPY 趋势同步性 | 两者 20日收益率方向 | 同向上升最高，同降最低 |

**广度修复（权重 25%）- ETF proxy 版**

| 因子 | 计算方法 | 评分方向 |
|---|---|---|
| 核心风险资产扩散度 | `SPY, QQQ, IWM, DIA` 中站上 MA50 与 MA200 的资产数量 | 越多越友好 |
| 行业 ETF 扩散度 | 行业 ETF universe 中，5日收益率为正或站上 MA50 的数量占比 | 越高越友好 |
| 进攻 / 防御比强弱 | `QQQ, IWM` 相对 `XLU, XLP, XLV` 的 10日表现 | 进攻占优更友好 |

**龙头确认（权重 15%）- ETF / 行业 proxy 版**

| 因子 | 计算方法 | 评分方向 |
|---|---|---|
| 大盘科技领导性 | QQQ vs SPY 10日相对动量 | 越高越友好 |
| 小盘确认度 | IWM vs SPY 10日相对动量 | 越高越友好 |
| 周期板块参与度 | XLE / XLB / XLF 相对 SPY 的 10日动量均值 | 周期参与越广越友好 |

**波动健康度（权重 20%）**

| 因子 | 计算方法 | 评分方向 |
|---|---|---|
| VIX 水位 | 252日百分位，反向 | VIX 分位越高，健康度越低 |
| VIX 变化趋势 | VIX 5日变化与 20日均值偏离 | 快速抬升降分，回落加分 |
| 风险信用代理 | JNK/LQD 与 JNK/SPY 相对强弱 | 高收益债越弱，健康度越低 |

### 2.2 分区与动作映射

| 分区 | 分值 | 总仓建议 |
|---|---|---|
| 防守区 | [0,35) | 0%-20% |
| 谨慎区 | [35,50) | 20%-40% |
| 试仓区 | [50,65) | 40%-60% |
| 进攻区 | [65,80) | 60%-80% |
| 强趋势区 | [80,100] | 80%-100% |

### 2.3 审计输出要求

长线环境卡必须输出 `factor_breakdown`。若 `LQD` 或 `JNK` 缺失，应将信用代理因子的 `data_status` 标为 `missing` 或 `proxy_used`，并降低 `confidence`。

---

## 3. 短线环境卡

### 3.1 因子量化映射

短线环境分越高，代表未来 1-5 个刷新周期内更适合主动交易。

**热点延续性（权重 30%）**

| 因子 | 计算方法 | 评分方向 |
|---|---|---|
| 行业 ETF 5日动量 vs 20日动量 | 5日超额动量 >0 的行业数占比 | 越高越友好 |
| 强势行业延续率 | 领先行业 ETF 在最近连续刷新中的相对强势是否保持 | 越稳定越友好 |
| 风格切换稳定度 | `QQQ, IWM, XLE, XLF` 等风格 ETF 最近 3-5 日强弱顺序是否稳定 | 越稳定越友好 |

**突破友好度（权重 25%）- ETF proxy 版**

| 因子 | 计算方法 | 评分方向 |
|---|---|---|
| ETF 突破持续率 | 主要 ETF 突破近20日高点后的近期延续表现 | 越高越友好 |
| ETF 放量守住率 | 突破日放量后是否守住突破位 | 越高越友好 |

**板块赚钱效应（权重 25%）- 行业 proxy 版**

| 因子 | 计算方法 | 评分方向 |
|---|---|---|
| 行业轮动连续性 | 近期领先行业 ETF 的相对强势是否延续 | 越连续越友好 |
| 高 Beta / 周期风格参与度 | `ARKK, IWM, XLE, XLF` 是否同步改善 | 越同步越友好 |
| 防御板块压制程度 | `XLU, XLP, XLV` 是否持续跑赢风险资产 | 防御跑赢越明显，短线进攻分越低 |

**波动友好度（权重 20%）**

| 因子 | 计算方法 | 评分方向 |
|---|---|---|
| SPY ATR% | 252日百分位 | 中位数最好，过低/过高均降分 |
| 隔夜缺口质量 | 近5日正向缺口占比与缺口后延续情况 | 正向延续越好越友好 |
| VIX 1日 / 5日变化 | VIX 快速抬升则降分 | 越低越友好 |

### 3.2 分区与动作映射

| 分区 | 分值 | 动作 |
|---|---|---|
| 极差区 | [0,20) | 禁止追涨，只等逆向机会 |
| 弱势区 | [20,35) | 轻仓试错，不隔夜高波动标的 |
| 观察区 | [35,50) | 可观察，不主动进攻 |
| 可做区 | [50,65) | 允许低吸、突破、事件交易 |
| 活跃区 | [65,80) | 允许提高交易频率 |
| 高胜率区 | [80,100] | 短线积极进攻，仍需风控 |

### 3.3 审计输出要求

短线卡必须标注 `data_mode`。若为 `daily`，不得使用“刷新时高低点”“尾盘回收率”等盘中语言；若为盘中模式，必须注明 interval、是否包含盘前盘后和数据延迟。

---

## 4. 系统风险卡

### 4.1 分数方向

`system_risk_score` 越高代表系统风险越高、越危险。系统风险卡与长线/短线卡方向相反，输出文案必须避免将风险分上升描述为“改善”。

### 4.2 两个子分

**流动性压力分（权重 50%）**

| 因子 | 类型 | 计算方法 | 评分方向 | 权重 |
|---|---|---|---|---|
| VIX 水位 | 慢变量 | 252日百分位 | 越高风险越高 | 35% |
| VIX 阶段性抬升速度 | 事件型 | 5日变化 / 20日基准 | 抬升越快风险越高 | 20% |
| IG 风险代理 | 慢变量 | LQD 相对 SPY / LQD 自身趋势位置 | LQD 相对走弱或跌破趋势，风险更高 | 20% |
| HY 风险代理 | 慢变量 | JNK/LQD、JNK/SPY、JNK 自身回撤 | JNK 相对走弱，风险更高 | 25% |

信用代理解释：
- `LQD` 代表投资级信用债风险偏好，明显走弱通常意味着信用压力上升。
- `JNK` 代表高收益债风险偏好，通常比 `LQD` 更敏感。
- `JNK/LQD` 上升通常代表信用风险偏好改善；下降通常代表高收益信用承压。
- `LQD/SPY` 上升不必然代表风险降低，可能只是股票更弱；应结合 LQD 自身趋势与 JNK/LQD 判断。

**风险偏好分（权重 50%）**

| 因子 | 类型 | 计算方法 | 评分方向 | 权重 |
|---|---|---|---|---|
| IWM/SPY 5日相对表现 | 慢变量 | 252日百分位 | IWM 相对弱，风险更高 | 30% |
| XLU/SPY 5日相对表现 | 慢变量 | 252日百分位 | XLU 相对强，避险更强，风险更高 | 25% |
| ARKK/SPY 5日相对表现 | 慢变量 | 高 Beta 风险偏好代理 | ARKK 相对弱，风险更高 | 20% |
| 跨资产同步下跌压力 | 慢变量 | SPY / QQQ / IWM / JNK 近5日共同走弱程度 | 同步走弱越强，风险越高 | 25% |

### 4.3 可选增强代理

若未来接入更完整数据，可加入但不作为当前硬依赖：

| 代理 | 作用 |
|---|---|
| `HYG` | 高收益债 ETF，常用信用风险 proxy，可与 JNK 互证 |
| `TLT, IEF, SHY` | 久期、避险和利率预期 proxy |
| `^TNX` | 10年期美债收益率压力 |
| `UUP` | 美元流动性压力 |
| `GLD` | 避险偏好参考 |

### 4.4 事件型风险触发原则

事件型风险触发必须结构化输出，不应只写“直接抬升 system_risk_score”。

```json
{
  "trigger_type": "macro_event",
  "event": "CPI release",
  "severity": "high",
  "score_impact": "+8",
  "confidence": 0.9,
  "expires_at": "2026-04-30T10:30:00-04:00"
}
```

事件型风险主要来自：
- VIX 单次刷新 / 5日快速抬升
- 风险资产与高收益债同步走弱
- 宏观事件或地缘风险搜索结果明显恶化

这些信号可作为执行卡收紧权限的依据，但必须保留 `trigger_type`、`severity`、`confidence` 和 `expires_at`。

### 4.5 分区与动作映射

| 分区 | 分值 | 动作 |
|---|---|---|
| 低压区 | [0,20) | 允许正常进攻 |
| 正常区 | [20,45) | 常规风控 |
| 压力区 | [45,60) | 缩仓、防追高、降单票风险 |
| 高压预警区 | [60,70) | 强制进入橙灯或更保守状态，禁止杠杆，降低新开仓权限 |
| 高压区 | [70,80) | 强制进入红灯-高压状态，只允许对冲或极低风险仓位 |
| 危机区 | [80,100] | 危机模式，只保留对冲或极低风险仓位 |

---

## 5. 市场手法与风格有效性卡

> 原“风格有效性卡”在 V2.3.1 中降调为“市场手法与风格有效性卡”。
> ETF proxy 能判断市场环境更支持哪类手法，但不能直接代表个股交易胜率。

### 5.1 第一层：策略手法有效性

回答问题：当前市场更适合用什么方式进场？

| 手法 | 计算方法 | 数据 | 评分方向 |
|---|---|---|---|
| 趋势突破 | `SPY, QQQ, IWM` 与主要行业 ETF 突破近20日高点后的近期延续表现 | 指数 / ETF 日线 | 越能延续越有效 |
| 回调低吸 | 主要 ETF 回踩 5-10 日均线或短期低点后的近期修复表现 | 指数 / ETF 日线 | 修复越稳定越有效 |
| 超跌反弹 | `SPY, QQQ, IWM, ARKK` 等高 Beta proxy basket 在短期急跌后的修复强度 | 指数 / ETF 日线 | 修复越强越有效 |

输出：`top_tactic`、`avoid_tactic`

### 5.2 第二层：资产风格偏好

回答问题：当前市场更偏好哪个方向？

| 风格 | 计算方法 | 数据 | 评分方向 |
|---|---|---|---|
| 大盘科技 | QQQ vs SPY 10日相对动量 | ETF 日线 | 越强越偏好 |
| 小盘高弹性 | IWM vs SPY 10日相对动量 | ETF 日线 | 越强越偏好 |
| 防御板块 | `(XLU + XLV + XLP) / 3` vs SPY 10日相对 | ETF 日线 | 防御越强，风险偏好越弱 |
| 能源/周期 | `(XLE + XLB) / 2` vs SPY 10日相对 | ETF 日线 | 越强越偏好 |
| 金融 | XLF vs SPY 10日相对 | ETF 日线 | 越强越偏好 |

输出：`preferred_assets`、`avoid_assets`

### 5.3 审计输出要求

```json
"style_effectiveness": {
  "tactic_layer": {
    "trend_breakout": {
      "score": 28,
      "valid": false,
      "delta_5d": -19,
      "factor_breakdown": []
    },
    "dip_buy": {
      "score": 66,
      "valid": true,
      "delta_5d": 11,
      "factor_breakdown": []
    },
    "oversold_bounce": {
      "score": 71,
      "valid": true,
      "delta_5d": 26,
      "factor_breakdown": []
    },
    "top_tactic": "回调低吸",
    "avoid_tactic": "趋势突破"
  },
  "asset_layer": {
    "preferred_assets": ["防御板块", "能源/周期"],
    "avoid_assets": ["小盘高弹性", "大盘科技"],
    "factor_breakdown": []
  }
}
```

---

## 6. 执行动作卡

### 6.1 决策优先级

执行卡必须按以下优先级裁决，不能只依赖矩阵枚举：

1. **系统风险 override**
   - `system_risk_score` 位于 `[60,70)`：强制进入橙灯或更保守状态，禁止杠杆，降低新开仓权限。
   - `system_risk_score` 位于 `[70,80)`：强制进入红灯-高压状态，只允许对冲或极低风险仓位。
   - `system_risk_score` 位于 `[80,100]`：强制进入红灯-危机状态，只保留对冲或极低风险仓位。

2. **长线环境**
   - 决定总仓位中枢和是否允许趋势仓。

3. **短线窗口**
   - 决定是否允许新开仓、追高、低吸、提高交易频率。

4. **市场手法与风格偏好**
   - 决定 `tactic_preference`、`preferred_assets`、`avoid_assets`。

5. **事件风险**
   - 指数级事件影响整体 regime 权限。
   - 个股级事件只影响该股，不污染指数 regime。

6. **panic 独立豁免**
   - panic 模块可在主评分卡未放宽时独立给出反弹试探仓。
   - panic 仓位必须单独管理，不得被误读为趋势仓恢复。

### 6.2 长线/短线冲突处理矩阵

| 长线 | 短线 | 系统风险 | Regime | 核心规则 |
|---|---|---|---|---|
| 强趋势（[80,100]） | 活跃（[65,100]） | 低（[0,25)） | 绿灯 | 允许 80%-100% 总仓，追高和隔夜允许 |
| 强（[65,80)） | 强（[55,100]） | 低（[0,35)） | 黄绿灯 | 进攻但不默认满仓，建议 60%-80% |
| 强（[65,80)） | 强（[55,100]） | 中（[35,60)） | 黄灯 | 进攻但控单票上限，减杠杆 |
| 强（[65,80)） | 弱（[25,45)） | 任意 | 黄灯-等待 | 趋势仓可保留，禁追高，只允许低吸 |
| 强（[65,80)） | 极差（[0,25)） | 任意 | 橙灯 | 趋势仓降风险，禁所有新开仓，等 panic 或短线修复 |
| 中性（[45,65)） | 强（[60,100]） | 低（[0,35)） | 黄绿灯-Swing | 允许积极 swing，不建趋势重仓 |
| 中性（[45,65)） | 中性（[45,55)） | 正常（[0,50)） | 黄灯 | 低频操作，低吸+确认突破，不提高频率 |
| 中性（[45,65)） | 弱（[0,45)） | 任意 | 橙灯 | 控仓，防守为主 |
| 弱（[0,45)） | 强（[55,100]） | 低（[0,35)） | 黄灯-短线 | 只允许短线博弈仓，不建趋势仓 |
| 弱（[0,45)） | 弱（[0,45)） | 任意 | 红灯 | 净值保护，禁一切新开仓 |
| 任意 | 任意 | 高压预警（[60,70)） | 橙灯 | 禁止杠杆，降低新开仓权限，优先保护净值 |
| 任意 | 任意 | 高压（[70,80)） | 红灯-高压 | 只允许对冲或极低风险仓位 |
| 任意 | 任意 | 危机（[80,100]） | 红灯-危机 | 危机模式，只保留对冲或极低风险仓位 |

矩阵未覆盖情形：
- 落入相邻更保守 regime。
- 在 `conflict_mode` 中说明 fallback 原因。
- 不得因为某一张卡强而忽略系统风险 override。

### 6.3 风险收紧 / 风险放宽机制

```text
主评分卡（长线/短线/系统风险）：
  风险收紧（risk tightening）：触发1次即生效，风险保护优先
  风险放宽（risk loosening）：需连续3次刷新保持后才放宽，防假突破

恐慌反转模块：
  可豁免主评分卡的3次风险放宽确认
  但必须满足 panic_confirmed 条件
  panic 仓位独立于趋势仓和 swing 仓
```

### 6.4 事件风险层：指数级 vs 个股级分离

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

### 6.5 执行卡输出要求

执行卡必须包含：
- `regime_label`
- `conflict_mode`
- `total_exposure_range`
- `new_position_allowed`
- `chase_breakout_allowed`
- `dip_buy_allowed`
- `overnight_allowed`
- `leverage_allowed`
- `single_position_cap`
- `daily_risk_budget`
- `tactic_preference`
- `preferred_assets`
- `avoid_assets`
- `signal_confirmation`
- `event_risk_flag`
- `confidence`
- `risks`
- `evidence`

---

## 7. 恐慌反转捕捉模块

### 7.1 分数方向与核心原则

`panic_extreme_score` 越高，只代表恐慌越强。恐慌充分不等于反转确认。
`panic_reversal_score` 越高，代表恐慌反弹机会越强，但仍必须满足衰竭或反弹确认条件。

### 7.2 四级状态设计

```text
无信号              panic_extreme_score < 35
panic_watch         恐慌出现但不极端，进入观察，不执行
capitulation_watch  恐慌极端，但尚未证明抛压衰竭，不执行反转仓
panic_confirmed     恐慌充分 + 抛压衰竭或即时反弹确认，可执行反弹仓
```

状态不是简单线性升级。`panic_confirmed` 必须通过确认门槛进入；`capitulation_watch` 不能因为恐慌更强而自动升级为 `panic_confirmed`。

### 7.3 第一段：恐慌程度计分

| 条件 | 类型 | 满足得分 |
|---|---|---|
| `SPY / QQQ / IWM / DIA` 任一指数型代理单次刷新跌幅 > 过去20次均值 × 2 | 事件型阈值 | 30分 |
| VIX 单次刷新涨幅 > 20% | 事件型阈值 | 25分 |
| 高 Beta proxy basket（`ARKK / IWM`）显著失速 | 事件型阈值 | 20分 |
| 系统风险卡 1次刷新 delta > +8 | 内部衍生指标 | 25分 |

```python
panic_extreme_score = sum(triggered_condition_scores)

if panic_extreme_score < 35:
    state = "无信号"
elif panic_extreme_score < 80:
    state = "panic_watch"
else:
    state = "capitulation_watch"
```

### 7.4 第二段：抛压衰竭分

盘中指标只能在 `intraday_delayed` 或 `intraday_realtime` 模式下使用。若 `data_mode = daily`，只能使用日线 OHLCV 的收盘位置与日成交量 proxy，不得声称盘中“脱离高位”。

| 因子 | 类型 | 计算方法 | 权重 |
|---|---|---|---|
| 区间回收率 | 恢复指标 | `(close - low) / (high - low)` | 35% |
| 成交量收缩迹象 | 事件型 | 当前成交量强度 < 最近恐慌刷新时段的 0.85 倍 | 20% |
| 领跌资产止跌 | 事件型 | `IWM / ARKK / XLE / XLF` 中至少两项跌幅显著收敛 | 25% |
| VIX 回落迹象 | 事件型 | 盘中模式下 VIX 脱离高位；日线模式下 VIX 收盘涨幅明显收敛 | 20% |

### 7.5 第三段：即时反弹确认分

反弹确认仅基于刷新当刻可见的指数 / ETF / 波动率行为，不依赖未来时点数据。

| 因子 | 类型 | 计算方法 | 权重 |
|---|---|---|---|
| 站回前一参考中位价 | 事件型 | `close > (prev_high + prev_low) / 2` | 35% |
| 收在当前区间上半部 | 事件型 | `close > low + 0.5 * (high - low)` | 30% |
| 高 Beta proxy basket 同步修复 | 事件型 | `ARKK / IWM` 表现明显优于刷新时低点 | 20% |
| 短线环境不再恶化 | 内部衍生 | `short_term_score` 明显止跌或回升 | 15% |

若 `data_mode = daily`，上述“刷新时低点”只能理解为当日或最近一根日线的 `low`，不得描述为盘中实时低点；若没有当日完整 OHLCV，则该因子应标记为 `missing` 或降权。

### 7.6 最终合成与状态机

```python
panic_reversal_score = (
    panic_extreme_score * 0.40 +
    selling_exhaustion_score * 0.30 +
    intraday_reversal_score * 0.30
)

if panic_extreme_score < 35:
    state = "无信号"
elif panic_reversal_score >= 50 and (selling_exhaustion_score >= 50 or intraday_reversal_score >= 60):
    state = "panic_confirmed"
elif panic_extreme_score >= 80:
    state = "capitulation_watch"
else:
    state = "panic_watch"
```

关键约束：
- `panic_extreme_score >= 80` 只能证明恐慌极端，不能单独证明反转。
- 必须满足 `selling_exhaustion_score >= 50` 或 `intraday_reversal_score >= 60`，才可进入 `panic_confirmed`。
- 若 `system_risk_score` 位于 `[80,100]`，即使 `panic_reversal_score >= 80`，反弹仓位上限也强制 `<=15%`。

### 7.7 分区与仓位

分区必须先看 `state`，再看对应分数。未确认状态使用 `panic_extreme_score` 判断观察等级；确认状态使用 `panic_reversal_score` 判断可用反弹仓位。

| 分区 | 分值 | 状态 | 动作 |
|---|---|---|---|
| 无信号 | `panic_extreme_score` [0,35) | 无信号 | 不操作 |
| 观察期 | `panic_extreme_score` [35,80) | panic_watch | 加入观察，不开仓 |
| 投降观察 | `panic_extreme_score` [80,100] | capitulation_watch | 恐慌极端但未确认，不开趋势仓、不默认抄底 |
| 一级试错 | `panic_reversal_score` [50,65) | panic_confirmed | 轻仓 10%-20%，允许即时试探 |
| 二级反弹 | `panic_reversal_score` [65,80) | panic_confirmed | 20%-35% |
| 强反转窗口 | `panic_reversal_score` [80,100] | panic_confirmed | 35%-50%（仅反弹策略仓） |

### 7.8 独立仓位管理规则

```text
即时试探规则：
  若 state = panic_confirmed 且 intraday_reversal_score >= 60：
    -> 允许刷新当刻建立 5%-10% 先手仓
  若后续刷新仍保持确认：
    -> 可把先手仓升级到一级试错或二级反弹仓位
  若后续刷新失去确认：
    -> 先手仓按更紧止损退出，不得硬扛

止损规则：
  止损比趋势仓更紧：ATR * 1.0
  若后续两次刷新后 panic 确认明显减弱：强制减仓50%

盈利兑现规则：
  达到 1R：兑现50%仓位
  剩余50%：止损移至成本线

持有时间规则：
  持有超过5次刷新周期自动触发警告
```

### 7.9 输出结构

```json
"panic_reversal_score": {
  "score": 64.0,
  "zone": "一级试错",
  "state": "panic_confirmed",
  "panic_extreme_score": 80.0,
  "selling_exhaustion_score": 55.0,
  "intraday_reversal_score": 42.0,
  "factor_breakdown": [],
  "action": "恐慌充分且抛压衰竭初现，可10%-15%轻仓试探",
  "system_risk_override": "系统风险位于[80,100]时，反弹仓上限强制<=15%",
  "stop_loss": "ATR*1.0",
  "profit_rule": "达1R兑现50%，余仓移止损至成本线",
  "timeout_warning": false,
  "refreshes_held": 0,
  "early_entry_allowed": false,
  "max_position_hint": "10%-20%",
  "confidence": 0.68,
  "risks": [],
  "evidence": []
}
```

---

## 8. 完整输出结构（V2.3.1）

```json
{
  "scorecard_version": "2.3.1",
  "prompt_version": "market-monitor-scorecard-2026-04-v2.3.1",
  "model_name": "gpt-5.4",
  "timestamp": "2026-04-09T16:00:00-04:00",
  "data_mode": "daily",
  "data_freshness": "daily_final",
  "input_data_status": {
    "core_symbols_available": ["SPY", "QQQ", "IWM", "DIA", "^VIX", "LQD", "JNK"],
    "core_symbols_missing": [],
    "interval": "1d",
    "includes_prepost": false,
    "source": "yfinance"
  },
  "missing_data": [],
  "risks": [],
  "event_fact_sheet": [
    {
      "event_id": "2026-04-10-cpi-release",
      "event": "CPI release",
      "scope": "index_level",
      "time_window": "tomorrow_before_open",
      "severity": "high",
      "source_type": "official_calendar",
      "source_name": "U.S. Bureau of Labor Statistics",
      "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
      "source_summary": "CPI 将于次日盘前公布，可能影响指数隔夜风险。",
      "observed_at": "2026-04-09T16:00:00-04:00",
      "confidence": 0.91,
      "expires_at": "2026-04-10T10:30:00-04:00"
    }
  ],

  "long_term_score": {
    "deterministic_score": 39.5,
    "score": 39.5,
    "zone": "谨慎区",
    "delta_1d": -4.2,
    "delta_5d": -16.1,
    "slope_state": "加速恶化",
    "recommended_exposure": "20%-40%",
    "factor_breakdown": [
      {
        "factor": "spy_ma200_distance",
        "raw_value": -0.018,
        "raw_value_unit": "ratio",
        "percentile": null,
        "polarity": "higher_is_better",
        "score": 10.0,
        "weight": 0.10,
        "reason": "SPY 接近但略低于200日均线，长线趋势偏弱。",
        "data_status": "available"
      }
    ],
    "score_adjustment": null,
    "confidence": 0.82,
    "risks": [],
    "evidence": []
  },

  "short_term_score": {
    "deterministic_score": 28.3,
    "score": 28.3,
    "zone": "弱势区",
    "delta_1d": -7.1,
    "delta_5d": -19.4,
    "slope_state": "加速恶化",
    "factor_breakdown": [],
    "score_adjustment": null,
    "confidence": 0.78,
    "risks": [],
    "evidence": []
  },

  "system_risk_score": {
    "deterministic_score": 69.1,
    "score": 74.1,
    "zone": "高压区",
    "liquidity_stress_score": 70.2,
    "risk_appetite_score": 78.0,
    "delta_1d": 10.3,
    "delta_5d": 26.5,
    "slope_state": "风险加速上升",
    "factor_breakdown": [
      {
        "factor": "vix_level",
        "raw_value": 28.4,
        "raw_value_unit": "index_points",
        "percentile": 86.0,
        "polarity": "higher_is_riskier",
        "score": 86.0,
        "weight": 0.35,
        "reason": "VIX 位于高分位，系统风险上升。",
        "data_status": "available"
      }
    ],
    "event_triggers": [
      {
        "trigger_type": "macro_event",
        "event": "CPI release",
        "severity": "high",
        "score_impact": "+5",
        "confidence": 0.91,
        "expires_at": "2026-04-10T10:30:00-04:00"
      }
    ],
    "score_adjustment": {
      "value": 5.0,
      "direction": "risk_up",
      "reason": "CPI 次日盘前公布，指数级隔夜事件风险上升。",
      "source_event_ids": ["2026-04-10-cpi-release"],
      "confidence": 0.91,
      "expires_at": "2026-04-10T10:30:00-04:00"
    },
    "confidence": 0.84,
    "risks": [],
    "evidence": []
  },

  "style_effectiveness": {
    "tactic_layer": {
      "trend_breakout": { "score": 22, "valid": false, "delta_5d": -21, "factor_breakdown": [] },
      "dip_buy": { "score": 63, "valid": true, "delta_5d": 10, "factor_breakdown": [] },
      "oversold_bounce": { "score": 75, "valid": true, "delta_5d": 28, "factor_breakdown": [] },
      "top_tactic": "超跌反弹",
      "avoid_tactic": "趋势突破"
    },
    "asset_layer": {
      "large_cap_tech": { "score": 29, "preferred": false, "delta_5d": -18 },
      "small_cap_momentum": { "score": 16, "preferred": false, "delta_5d": -25 },
      "defensive": { "score": 84, "preferred": true, "delta_5d": 23 },
      "energy_cyclical": { "score": 65, "preferred": true, "delta_5d": 11 },
      "financials": { "score": 41, "preferred": false, "delta_5d": -6 },
      "preferred_assets": ["防御板块", "能源/周期"],
      "avoid_assets": ["小盘高弹性", "大盘科技"],
      "factor_breakdown": []
    },
    "confidence": 0.76,
    "risks": [],
    "evidence": []
  },

  "execution_card": {
    "regime_label": "红灯",
    "conflict_mode": "长弱短弱+系统风险高压，系统风险 override 生效",
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
    "avoid_assets": ["小盘高弹性", "高Beta追涨"],
    "signal_confirmation": {
      "current_regime_observations": 1,
      "risk_loosening_unlock_in_observations": 2,
      "note": "当前仍处于风险收紧状态，需再连续2次刷新保持后才可评估放宽"
    },
    "event_risk_flag": {
      "index_level": {
        "active": true,
        "events": ["CPI release"],
        "source_event_ids": ["2026-04-10-cpi-release"],
        "action_modifier": {
          "new_position_allowed": null,
          "overnight_allowed": false,
          "single_position_cap_multiplier": 0.8,
          "note": "CPI 次日盘前公布，隔夜权限收紧。"
        }
      },
      "stock_level": {
        "earnings_stocks": ["NVDA"],
        "rule": "NVDA 财报 T-1，单票上限减半，不影响 regime"
      }
    },
    "confidence": 0.83,
    "risks": [],
    "evidence": []
  },

  "panic_reversal_score": {
    "score": 64.0,
    "zone": "一级试错",
    "state": "panic_confirmed",
    "panic_extreme_score": 80.0,
    "selling_exhaustion_score": 55.0,
    "intraday_reversal_score": 42.0,
    "factor_breakdown": [],
    "action": "恐慌充分且抛压衰竭初现，可10%-15%轻仓试探",
    "system_risk_override": "系统风险位于[80,100]时，反弹仓上限强制<=15%",
    "stop_loss": "ATR*1.0",
    "profit_rule": "达1R兑现50%，余仓移止损至成本线",
    "timeout_warning": false,
    "refreshes_held": 0,
    "early_entry_allowed": false,
    "max_position_hint": "10%-20%",
    "confidence": 0.68,
    "risks": [],
    "evidence": []
  }
}
```

---

## 9. 回测、校准与复盘标准

### 9.1 Regime 校准目标

未来调参必须基于回测统计，而不是人工感觉调阈值。至少应跟踪：

- 每个 `regime_label` 后 1 / 5 / 20 个交易日的 `SPY, QQQ, IWM` 收益分布
- 每个 regime 的最大回撤、胜率、盈亏比、假信号率
- 红灯 / 橙灯期间的回撤规避效果
- 绿灯 / 黄绿灯期间的收益捕获效率
- 系统风险 override 的触发频率与误伤率

### 9.2 Panic 模块单独校准

panic 模块必须单独评估，不能和趋势仓表现混在一起：

- `panic_confirmed` 后 1R 达成率
- `panic_confirmed` 后止损率
- 平均持有刷新周期
- `capitulation_watch` 未确认时继续下跌的比例
- `system_risk_score` 位于 `[80,100]` 时，15% 仓位上限是否有效降低尾部风险

### 9.3 LLM 复盘要求

每次评分卡输出应保留可复盘信息：

- `scorecard_version`
- `prompt_version`
- `model_name`
- `factor_breakdown`
- `event_fact_sheet`
- `missing_data`
- `confidence`
- `evidence`

失败样本复盘时，应回答：
- 哪些因子方向判断错误？
- 哪些事件事实过期或置信度过高？
- 哪些搜索结果污染了本地结构化判断？
- 哪些阈值需要回测校准？
- LLM 是否越权编造或覆盖了本地指标？

### 9.4 版本升级原则

- 小幅阈值校准可升级 patch 版本，例如 V2.3.1。
- 输出结构字段变更应升级 minor 版本，例如 V2.4。
- 分数方向、状态机、执行优先级改变应升级 major 或明确迁移说明。
