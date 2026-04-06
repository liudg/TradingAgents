# 历史回测与 LLM 复盘系统

## 目标

这套系统用于把 TradingAgents 的单次分析能力扩展成可批量验证的研究闭环：

1. 按历史交易日批量重放过去的分析流程。
2. 用统一口径评估 `BUY / HOLD / SELL` 的后续表现。
3. 对关键成功和失败样本触发 LLM 结构化复盘。
4. 将高价值结论写回 memory，供后续交易 agent 检索。

第一版只在 Web UI 层提供入口，不修改 CLI。

## MVP 闭环

系统分为四个阶段：

- `historical_run`
  对指定 `ticker + start_date + end_date` 范围内的有效交易日逐日调用 `TradingAgentsGraph.propagate(...)`。
- `evaluate`
  用未来价格路径为每个样本计算收益、基准收益、超额收益和最大回撤。
- `reflect`
  对显著成功或失败样本生成结构化复盘，输出固定字段：
  `decision_quality`、`key_success_factors`、`key_failure_factors`、`what_should_change`、`reusable_rule`、`memory_query`、`confidence`。
- `memory_writeback`
  只把高价值样本写回 `trader_memory`，避免把普通样本全部灌入记忆库。

## 评估口径

- 交易日范围由历史价格数据决定，非交易日自动跳过。
- `BUY`
  分析日后的下一个交易日开盘建仓，固定持有 `holding_period` 个交易日，在最后一天收盘平仓。
- `HOLD`
  记为 0 仓位收益，同时计算对应区间的标的基准收益，用于判断是否错过机会或规避亏损。
- `SELL`
  第一版仅保留信号，不纳入正式收益统计，避免把做空语义和回测口径混在一起。
- `benchmark_return_pct`
  用分析日收盘到退出日收盘的标的价格变化计算。

## 数据产物

每个回测实验都会生成独立目录，包含：

- `backtest.log`
  阶段日志和失败栈。
- `runs/<trade_date>/reports/`
  每个样本的 markdown 报告。
- `backtest_results.json`
  汇总指标、单笔样本、复盘结果和 memory 写回结果。
- `backtest_snapshot.json`
  Web API 用于恢复历史任务的快照。

原有 `eval_results/...` 继续保留，作为 graph 运行状态快照。

## Web API

新增接口：

- `POST /api/backtest-jobs`
- `GET /api/backtest-jobs/{job_id}`
- `GET /api/backtest-jobs/{job_id}/logs`
- `GET /api/historical-backtests`
- `GET /api/historical-backtests/{job_id}`

任务状态沿用现有异步模型：`pending`、`running`、`completed`、`failed`。

## Memory 写回策略

仅当样本满足以下条件时才写回 memory：

- 明显失败样本：`incorrect` 或 `missed_opportunity`
- 或显著成功样本：`excess_return_pct >= 4`

第一版只写入 `trader_memory`。原因是当前项目的 memory 机制是轻量 BM25，本轮先验证“回测能否产出有价值经验”，不同时把多个角色的 memory 一起放大。

## 风险与限制

- 必须避免未来数据泄漏，分析运行只使用分析日之前可见的数据。
- `SELL` 暂不计入正式收益，后续如要支持，需要单独定义做空回测语义。
- LLM 结构化复盘允许回退到规则模板，避免 JSON 解析失败时整批任务中断。
- memory 虽然已经持久化，但第一版没有提供 memory 管理 UI。
