# Market Monitor Implementation Plan

## 1. 目标

基于 [market-scorecard-v2.2.md](/E:/document/TradingAgents/docs/market-scorecard-v2.2.md) 实现一套完整的市场监控系统，服务对象为美股 `核心指数/风格 ETF + 主要行业 ETF`。

本次实施遵守以下边界：

- 所有后端逻辑仅放在 [tradingagents/web](/E:/document/TradingAgents/tradingagents/web)
- 前端展示仅落在 [MarketMonitorPage.tsx](/E:/document/TradingAgents/web-ui/src/pages/MarketMonitorPage.tsx)
- 不复用现有分析 agent，不依赖 `TradingAgentsGraph`、`market_analyst` 或其他 LLM agent 参与评分
- 评分、状态机、动作卡、恐慌反转模块全部以确定性规则重新实现

## 2. 范围定义

### 2.1 监控范围

核心指数与风格 ETF：

- `SPY`
- `QQQ`
- `IWM`
- `DIA`
- `ARKK`

主要行业 ETF：

- `XLK`
- `XLY`
- `XLC`
- `XLI`
- `XLF`
- `XLV`
- `XLE`
- `XLB`
- `XLU`
- `XLP`
- `XLRE`

代理池：

- 核心指数与风格 ETF
- 主要行业 ETF

### 2.2 功能范围

必须实现：

- 长线环境卡
- 短线环境卡
- 系统风险卡
- 风格有效性卡（策略手法层 + 资产风格层）
- 执行动作卡
- 恐慌反转模块
- 指数级 / 个股级事件风险层
- 历史趋势回看
- 数据完整度与降级提示

MVP 可延后：

- CBOE 全量波动结构深度增强
- 更完整的市场广度来源
- LLM 市场解读摘要

## 3. 架构原则

### 3.1 纯规则引擎

所有评分逻辑都实现为纯函数或轻状态服务：

- 输入：市场数据、ETF/指数代理池数据、事件日历、缓存上下文
- 输出：标准化评分卡 JSON

禁止：

- 让 agent 生成卡片分数
- 让 agent 决定 regime
- 让 agent 决定 panic 状态

### 3.2 Web 边界封装

虽然部分抓数逻辑与 dataflows 类似，但本次不得侵入其他模块。  
因此所有新增数据采集、缓存、规则计算都放在 `tradingagents/web` 下单独维护。

### 3.3 先可运行，再补完整

MVP 优先保证：

- 页面可用
- 数据结构稳定
- 规则口径一致
- 数据缺失时可降级

不要求第一版覆盖全部理想因子。

## 4. 现有项目能力评估

### 4.1 可以借鉴但不复用的部分

现有项目中以下能力可作为参考，但本次不直接复用业务逻辑：

- [tradingagents/web/app.py](/E:/document/TradingAgents/tradingagents/web/app.py)
- [tradingagents/web/schemas.py](/E:/document/TradingAgents/tradingagents/web/schemas.py)
- [tradingagents/dataflows/interface.py](/E:/document/TradingAgents/tradingagents/dataflows/interface.py)
- [tradingagents/dataflows/y_finance.py](/E:/document/TradingAgents/tradingagents/dataflows/y_finance.py)

说明：

- Web API 的组织方式可以复用
- 现有数据抓取方式可以参考
- 但 market monitor 的业务层全部重新实现，不与现有分析链路耦合

### 4.2 当前缺口

项目当前没有：

- 市场评分卡引擎
- 市场广度扫描服务
- 恐慌反转模块
- 指数级事件日历层
- 面向 `MarketMonitorPage` 的 API

因此本功能属于新增子系统，而非对现有 agent 流程的小修。

## 5. 后端设计

## 5.1 模块划分

所有新增代码放在 [tradingagents/web](/E:/document/TradingAgents/tradingagents/web)。

建议新增以下模块：

- `market_monitor_schemas.py`
- `market_monitor_service.py`
- `market_monitor_cache.py`
- `market_monitor_universe.py`
- `market_monitor_data.py`
- `market_monitor_indicators.py`
- `market_monitor_scoring.py`
- `market_monitor_panic.py`
- `market_monitor_calendar.py`
- `market_monitor_history.py`

### 5.1.1 `market_monitor_schemas.py`

定义所有请求/响应模型：

- `MarketMonitorSnapshotRequest`
- `MarketMonitorSnapshotResponse`
- `MarketScoreCard`
- `MarketStyleEffectiveness`
- `MarketExecutionCard`
- `MarketPanicReversalCard`
- `MarketEventRiskFlag`
- `MarketSourceCoverage`
- `MarketHistoryPoint`

### 5.1.2 `market_monitor_service.py`

系统总入口，负责：

- 接收 API 请求
- 检查缓存
- 调用数据层
- 调用指标层
- 调用评分层
- 聚合最终结构

### 5.1.3 `market_monitor_cache.py`

实现轻量缓存：

- 日线缓存
- 分钟线缓存
- snapshot 缓存
- 历史快照缓存

建议第一版使用：

- 内存缓存 + 可选文件缓存

### 5.1.4 `market_monitor_universe.py`

管理 ETF/指数代理池：

- 内置核心指数与风格 ETF 列表
- 内置行业 ETF 列表
- 提供按用途分组的代理池接口

### 5.1.5 `market_monitor_data.py`

负责所有市场数据获取：

- ETF/指数日线
- 恐慌模块所需分钟线
- 跨资产代理数据
- 数据缺失 fallback

### 5.1.6 `market_monitor_indicators.py`

负责全部基础指标计算：

- 滚动百分位
- MA 偏离
- MA 斜率
- ATR%
- 3 月区间位置
- 相对动量
- 广度统计
- 风格强弱

### 5.1.7 `market_monitor_scoring.py`

负责：

- 长线环境卡
- 短线环境卡
- 系统风险卡
- 风格卡两层
- 执行动作卡
- 冲突矩阵

### 5.1.8 `market_monitor_panic.py`

负责：

- `panic_extreme_score`
- `selling_exhaustion_score`
- `intraday_reversal_score`
- `followthrough_confirmation_score`
- `panic_watch`
- `panic_confirmed`
- early entry 规则
- 仓位 override

### 5.1.9 `market_monitor_calendar.py`

负责：

- 指数级事件
- 个股级事件
- 事件风险 modifier

### 5.1.10 `market_monitor_history.py`

负责：

- 保存历史 snapshot
- 生成页面趋势视图所需的最近 N 天数据

## 5.2 API 设计

在 [app.py](/E:/document/TradingAgents/tradingagents/web/app.py) 中新增接口：

- `GET /api/market-monitor/snapshot`
- `POST /api/market-monitor/snapshot`
- `GET /api/market-monitor/history`
- `GET /api/market-monitor/data-status`

### 5.2.1 `GET /api/market-monitor/snapshot`

用途：

- 获取最新市场评分卡

建议参数：

- `as_of_date`
- `force_refresh`

### 5.2.2 `POST /api/market-monitor/snapshot`

用途：

- 主动请求按某交易日重算 snapshot

### 5.2.3 `GET /api/market-monitor/history`

用途：

- 获取最近 N 个交易日的核心分数与 regime 演变

建议参数：

- `days`

### 5.2.4 `GET /api/market-monitor/data-status`

用途：

- 返回当前数据源可用性、缺失因子、降级说明

## 6. 数据实现方案

## 6.1 数据源策略

本期不改造 `dataflows`，而是在 `web` 里单独包装数据抓取。

MVP 数据优先级：

- ETF/指数/个股日线：必做
- ETF/指数分钟线：恐慌模块必做，但仅少量标的
- 事件日历：必做简化版
- PCR/VIX 扩展：可先做部分支持

## 6.2 代理池与横截面

采用：

- 核心指数与风格 ETF 作为市场状态与风格代理主池
- 行业 ETF 作为 breadth、轮动、风格层主池

理由：

- 足够代表科技、风险偏好与行业轮动
- 请求成本显著低于股票横截面扫描
- 对美股 regime 变化足够敏感
- 更适合第一版做稳定、可缓存、可扩展的实现

## 6.3 MVP 数据字段覆盖

### 长线卡需要

- SPY、QQQ 日线
- MA50、MA200
- 3 月区间高低点
- ETF/指数代理池站上 MA200 占比
- 新高 / 新低简化统计

### 短线卡需要

- 行业 ETF 5d / 20d 动量
- ETF/指数代理池突破后延续统计
- ETF/指数代理池回调低吸样本统计
- SPY ATR%
- SPY 隔夜缺口质量

### 系统风险卡需要

- IWM/SPY
- XLU/SPY
- 防御篮子 vs SPY
- 跨资产方向一致性
- 可得时补充 VIX / PCR

### 风格卡需要

- 手法层：
  - 趋势突破
  - 回调低吸
  - 超跌反弹
- 资产层：
  - 大盘科技
  - 小盘高弹性
  - 防御板块
  - 能源/周期
  - 金融

### 恐慌模块需要

- SPY / QQQ / IWM / ARKK 日线
- 至少 SPY / QQQ / IWM 分钟线
- 尾盘修复结构
- 次日延续确认结构

## 6.4 数据降级策略

当部分数据缺失时：

- 不抛硬错误
- 回退到降级因子
- 在响应里输出：
  - `source_coverage`
  - `degraded_factors`
  - `notes`

例如：

- 缺 `PCR` 时，系统风险卡仍可运行，但风险情绪维度降级
- 缺分钟线时，panic 模块仅保留日线确认，不给 early entry

## 7. 评分引擎开发顺序

## 7.1 第一优先级

- 长线环境卡
- 系统风险卡
- 执行动作卡

原因：

- 这是整页最核心的 regime 框架

## 7.2 第二优先级

- 短线环境卡
- 风格有效性卡

原因：

- 决定“可不可以做”和“做什么”

## 7.3 第三优先级

- 恐慌反转模块

原因：

- 逻辑更复杂，涉及分钟线和早期入场

## 7.4 第四优先级

- 历史趋势
- 数据状态页
- 事件风险增强

## 8. 前端实现方案

前端展示只写在 [MarketMonitorPage.tsx](/E:/document/TradingAgents/web-ui/src/pages/MarketMonitorPage.tsx)。

但为了接入 API，允许新增：

- [client.ts](/E:/document/TradingAgents/web-ui/src/api/client.ts)
- [hooks.ts](/E:/document/TradingAgents/web-ui/src/api/hooks.ts)
- [types.ts](/E:/document/TradingAgents/web-ui/src/api/types.ts)

## 8.1 页面结构

### 顶部总览区

展示：

- `regime_label`
- `conflict_mode`
- 数据时间
- 刷新按钮
- 数据完整度

### 第一排主卡

- 长线环境卡
- 短线环境卡
- 系统风险卡

### 第二排决策卡

- 风格有效性卡
- 执行动作卡

### 第三排重点卡

- 恐慌反转模块

### 第四排辅助区

- 指数级事件风险
- 个股级事件风险
- 数据降级说明

### 底部趋势区

- 最近 N 日评分变化
- regime 历史切换

## 8.2 页面展示原则

每张主卡必须显示：

- 当前分数
- 当前区间
- `delta_1d`
- `delta_5d`
- `slope_state`
- 动作建议

执行卡必须突出：

- 总仓位范围
- 新开仓是否允许
- 追高是否允许
- 低吸是否允许
- 杠杆是否允许
- 单票上限
- 风险预算

panic 卡必须突出：

- 当前状态
- 是否允许 early entry
- 当前仓位上限
- 止损规则
- 盈利兑现规则

## 9. 分阶段开发计划

## 9.1 Phase 1：后端骨架与 API（1 周）

目标：

- 把 API 和 schema 搭起来
- 先返回最小可用结构

任务：

- 新增 market monitor schemas
- 新增 service 入口
- 在 app.py 注册新路由
- 增加基础缓存
- 先返回 mock / fallback snapshot

完成标准：

- `MarketMonitorPage` 可请求到后端结构化数据

## 9.2 Phase 2：MVP 数据层与三张核心卡（1-1.5 周）

目标：

- 拿到核心 ETF / 行业 ETF / 跨资产代理数据
- 打通长线、短线、系统风险卡

任务：

- 实现 universe
- 实现 ETF / 指数代理日线抓取
- 实现基于代理池的 breadth 统计
- 实现长线、短线、系统风险评分

完成标准：

- 三张主卡分数可稳定输出

## 9.3 Phase 3：风格卡与执行卡（1 周）

目标：

- 让评分真正能指导动作

任务：

- 实现手法层
- 实现资产层
- 实现冲突矩阵
- 实现 regime label
- 实现执行卡动作映射

完成标准：

- execution_card 可直接用于页面展示

## 9.4 Phase 4：恐慌反转模块（1 周）

目标：

- 完成 `panic_watch / panic_confirmed`

任务：

- 实现 panic 三段式
- 实现 intraday/followthrough 双确认
- 实现 early entry
- 实现仓位 override

完成标准：

- panic 模块口径与文档完全一致

## 9.5 Phase 5：前端页面完成（1 周）

目标：

- MarketMonitorPage 可作为市场监控首页使用

任务：

- 完成 API 类型与 hooks
- 完成 MarketMonitorPage 主布局
- 完成 loading/error/partial 状态
- 完成历史趋势区

完成标准：

- 页面可读、可刷新、可定位风险状态

## 9.6 Phase 6：增强与验证（1-2 周）

目标：

- 增强数据覆盖和稳定性

任务：

- 事件风险层增强
- 数据缺失降级验证
- 增加测试
- 调整阈值

## 10. 测试计划

## 10.1 后端测试

重点覆盖：

- 百分位映射
- 阶梯分映射
- 长短冲突矩阵
- 执行动作卡状态机
- panic 状态机
- panic 分区与状态一致性
- 数据缺失时的降级路径

## 10.2 前端测试

重点覆盖：

- 页面加载态
- 错误态
- 数据部分缺失态
- 红灯 / 黄灯 / 黄绿灯-Swing / panic_confirmed 展示

## 11. 风险与注意事项

### 11.1 最大风险

数据源覆盖不完整，尤其是：

- PCR
- VIX 期限结构
- 分钟线
- 事件日历

### 11.2 应对策略

- 第一版优先把可得数据做稳
- 缺失部分通过 `source_coverage` 明确展示
- 不为了追求满配因子拖慢上线

### 11.3 明确不做

本次不做：

- 评分依赖 LLM
- 复用现有分析 agent 生成市场卡片
- 改造 graph/agents/dataflows 核心模块

## 12. 文件级任务清单

## 12.1 后端文件

### [tradingagents/web/app.py](/E:/document/TradingAgents/tradingagents/web/app.py)

任务：

- 注册 market monitor 相关 API
- 补充错误处理
- 接入 market monitor service

### [tradingagents/web/market_monitor_schemas.py](/E:/document/TradingAgents/tradingagents/web/market_monitor_schemas.py)

任务：

- 定义全部请求/响应模型
- 定义 score card 与 panic card 子结构
- 定义 source coverage 与 history 点位模型

### [tradingagents/web/market_monitor_service.py](/E:/document/TradingAgents/tradingagents/web/market_monitor_service.py)

任务：

- 实现 snapshot 主流程
- 串联数据层、指标层、评分层、缓存层
- 输出最终响应

### [tradingagents/web/market_monitor_cache.py](/E:/document/TradingAgents/tradingagents/web/market_monitor_cache.py)

任务：

- 实现内存缓存
- 定义 TTL
- 封装 snapshot 与数据缓存接口

### [tradingagents/web/market_monitor_universe.py](/E:/document/TradingAgents/tradingagents/web/market_monitor_universe.py)

任务：

- 内置核心指数/风格 ETF 池
- 内置 ETF 池
- 提供按用途分组的 universe 接口

### [tradingagents/web/market_monitor_data.py](/E:/document/TradingAgents/tradingagents/web/market_monitor_data.py)

任务：

- 拉 ETF / 指数代理日线
- 拉恐慌模块所需分钟线
- 拉跨资产代理数据
- 输出标准化 dataframe / dict 结构

### [tradingagents/web/market_monitor_indicators.py](/E:/document/TradingAgents/tradingagents/web/market_monitor_indicators.py)

任务：

- 百分位工具函数
- 阶梯分函数
- MA / ATR / RS / 区间位置计算
- 广度和风格指标计算

### [tradingagents/web/market_monitor_scoring.py](/E:/document/TradingAgents/tradingagents/web/market_monitor_scoring.py)

任务：

- 长线环境卡
- 短线环境卡
- 系统风险卡
- 风格卡
- 执行动作卡

### [tradingagents/web/market_monitor_panic.py](/E:/document/TradingAgents/tradingagents/web/market_monitor_panic.py)

任务：

- panic extreme
- selling exhaustion
- intraday reversal
- followthrough confirmation
- panic 状态机
- early entry 规则

### [tradingagents/web/market_monitor_calendar.py](/E:/document/TradingAgents/tradingagents/web/market_monitor_calendar.py)

任务：

- 指数级事件风险
- 个股级事件风险
- modifier 生成

### [tradingagents/web/market_monitor_history.py](/E:/document/TradingAgents/tradingagents/web/market_monitor_history.py)

任务：

- 保存最近 N 日 snapshot
- 输出历史趋势数据

## 12.2 前端文件

### [web-ui/src/api/types.ts](/E:/document/TradingAgents/web-ui/src/api/types.ts)

任务：

- 新增 market monitor 响应类型
- 定义 score card、execution card、panic card、history point 类型

### [web-ui/src/api/client.ts](/E:/document/TradingAgents/web-ui/src/api/client.ts)

任务：

- 新增 fetchMarketMonitorSnapshot
- 新增 fetchMarketMonitorHistory
- 新增 fetchMarketMonitorDataStatus

### [web-ui/src/api/hooks.ts](/E:/document/TradingAgents/web-ui/src/api/hooks.ts)

任务：

- 新增 useMarketMonitorSnapshot
- 新增 useMarketMonitorHistory
- 新增 useMarketMonitorDataStatus

### [web-ui/src/pages/MarketMonitorPage.tsx](/E:/document/TradingAgents/web-ui/src/pages/MarketMonitorPage.tsx)

任务：

- 实现完整监控页布局
- 对接 snapshot / history / data-status
- 实现卡片、风险提示、趋势区、panic 模块展示

### [web-ui/src/styles.css](/E:/document/TradingAgents/web-ui/src/styles.css)

任务：

- 如现有样式不够，补充市场监控页局部样式
- 保持和现有页面风格一致

## 12.3 测试文件

建议新增：

- `tests/test_market_monitor_indicators.py`
- `tests/test_market_monitor_scoring.py`
- `tests/test_market_monitor_panic.py`
- `tests/test_market_monitor_api.py`

任务：

- 覆盖规则引擎核心行为
- 覆盖 API 结构与异常场景

## 13. 建议实施顺序

推荐按以下顺序开始：

1. schema 定义
2. service 骨架
3. universe + data
4. indicators
5. scoring
6. panic
7. app API
8. 前端 types/client/hooks
9. MarketMonitorPage
10. tests

这样可以保证每一步都有清晰的输入输出，不会前后端互相等待太久。
