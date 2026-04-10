# Market Monitor 进度表

## 概览

本文档用于跟踪 market monitor 相对以下需求文档的当前完成状态：

- `docs/market-scorecard-v2.2.md`
- `docs/market-monitor-implementation-plan.md`

当前整体完成度估计：`约 65%`

说明：

- 这里的百分比是相对于 `docs/market-scorecard-v2.2.md` 和 `docs/market-monitor-implementation-plan.md` 的完整目标估算，不是“主链路是否能跑通”的完成度。
- “已完成主干”表示核心链路、基础 API、基础前端和必要缓存已经打通，可稳定跑通 MVP；不代表增强因子、完整 panic 机制、事件日历、历史 snapshot 体系等都已完成。

## 完成度表

| 模块 | 完成度 | 当前状态 |
|---|---:|---|
| 长线环境卡 | 85% | 主链路已完成，能稳定输出分数、分区、斜率、涨跌变化和动作建议。ETF/指数代理 breadth 已确定为最终方案。当前主要缺少少量增强因子与更细的展示说明。 |
| 短线环境卡 | 75% | 主链路已完成，能稳定输出。当前主要基于行业 ETF 动量扩散、SPY 波动代理、gap 代理和 breadth 代理；代理池统计将作为最终方案保留。 |
| 系统风险卡 | 65% | MVP 已完成，当前基于 `IWM/SPY`、`XLU/SPY`、breadth stress 和 `VIX`。`PCR`、`VVIX/VIX`、信用利差、VIX 期限结构等关键增强因子尚未接入。 |
| 风格有效性卡 | 70% | 两层结构已完成并可展示。tactic layer 使用 ETF/指数代理版，这也是当前确定的最终方向。 |
| 执行动作卡 | 80% | `regime`、总仓位、动作开关、单票上限、风险预算等都已实现，是当前最完整的决策层之一。冲突矩阵和持久化确认逻辑仍为简化版。 |
| Panic Reversal 模块 | 35% | 卡片结构、分数、状态和 early entry 字段已具备。当前逻辑仍是简化版，尚未达到文档要求的三段式完整实现。 |
| 事件风险层 | 20% | schema 和响应结构已具备，但尚未接入真实日历数据，也没有落实指数级/个股级事件修正规则。 |
| 历史趋势回看 | 55% | history API 已实现，可返回最近若干日的分数与 regime 变化。当前仍依赖简化版评分引擎，而不是完整的历史 snapshot 体系。 |
| 数据完整度/降级提示 | 70% | `source_coverage`、`degraded_factors`、`notes` 等已实现并对外暴露。当前降级逻辑仍比较粗。 |
| Snapshot API | 80% | 已完成且稳定，包含 symbol 缓存、snapshot 缓存和 dataset 复用。 |
| History API | 70% | 已完成且稳定，基于当前简化版评分链路输出历史结果。 |
| Data Status API | 75% | 已完成且稳定，能优先复用 snapshot cache。 |
| 前端监控页 | 70% | 主评分卡、最终决策、panic、data status、history 均可展示。当前呈现仍偏 MVP 版本。 |

## 按状态分类

### 已完成主干

说明：这里的“主干”是指 MVP 主链路已打通，不等于对应模块已经达到 100% 需求完成度。

- 长线环境卡
- 短线环境卡
- 系统风险卡
- 执行动作卡
- Snapshot API
- History API
- Data Status API
- 基础前端展示
- 必要缓存

### 简化版可用

- 风格有效性卡
- Panic Reversal 模块
- 历史趋势展示
- 数据降级提示

### 明显未完成

- 事件风险层
- PCR / VIX 期限结构 / 信用利差风险因子
- 分钟级 panic 确认
- 完整的持久化确认与延迟机制
- 更细的代理池战法统计增强

## 距离完整需求的主要差距

- 系统风险高级因子尚未补齐。
- Panic Reversal 仍是 MVP 近似实现。
- 事件日历集成尚未落地。
- 风格和战法评分已确定采用代理池路线，后续主要是增强代理因子，而不是回到股票横截面方案。
