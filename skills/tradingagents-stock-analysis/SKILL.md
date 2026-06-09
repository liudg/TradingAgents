---
name: tradingagents-stock-analysis
description: 通过本地子进程调用 TradingAgents 默认股票分析，返回最终 Markdown 投资结论，并在 TradingAgents logs 目录保存完整分层报告。Use when 用户要求用当前 TradingAgents 项目分析某个具体股票或 ticker、生成默认股票分析报告/投资结论，或明确点名 tradingagents-stock-analysis skill。
---

# TradingAgents 股票分析

## 用途

当需要调用本项目的股票分析能力时，使用本地 CLI 子进程执行分析。该 skill 只传入股票代码，项目使用默认配置完成分析，把最终投资结论 Markdown 返回给调用方，并在 TradingAgents logs 目录保存完整分层报告。

适用场景：

- 用户给出一个明确股票代码，并要求用 TradingAgents 做股票分析。
- 用户要求生成默认股票分析报告、投资结论或 Markdown 结论。
- 用户明确要求使用 `tradingagents-stock-analysis` skill。

## 调用命令

```powershell
E:\document\tradingAgents\.venv\Scripts\python.exe E:\document\tradingAgents\skill-cli\tradingagents_skill.py stock-analysis <ticker>
```

示例：

```powershell
E:\document\tradingAgents\.venv\Scripts\python.exe E:\document\tradingAgents\skill-cli\tradingagents_skill.py stock-analysis AAPL
```

## 输入

- `<ticker>`：必填，待分析股票代码。
- 允许字符：`A-Z`、`0-9`、`.`、`-`、`_`。
- 最大长度：32 个字符。

## 输出

成功时：

- 退出码为 `0`。
- `stdout` 只包含最终结论 Markdown 文本。
- 调用方应直接读取 `stdout` 作为分析结果。
- 完整报告会保存到 `DEFAULT_CONFIG["results_dir"]` 下的 `<ticker>/<trade_date>/<job_id>/reports/complete_report.md`，同时生成 `1_analysts`、`2_research`、`3_trading`、`4_risk`、`5_portfolio` 子目录。
- 同一 `<ticker>/<trade_date>/<job_id>/` 目录会生成 `job_snapshot.json` 和 `message_tool.log`，便于 Web 历史报告入口识别。
- 完整报告路径会写入 `stderr`，格式为 `完整报告已保存: <path>`。

进度、日志、完整报告路径、告警和错误说明会写入 `stderr`，不要把 `stderr` 拼入最终 Markdown。

## 失败处理

调用方应同时检查退出码和 `stderr`：

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功，`stdout` 为最终 Markdown |
| `2` | 参数错误，例如缺少 ticker 或 ticker 格式非法 |
| `3` | 环境或配置错误，例如项目依赖不可用 |
| `4` | 分析运行失败，例如数据源、模型调用或图执行失败 |

失败时不要使用 `stdout` 作为报告内容；应读取 `stderr` 获取原因。

## 约束

- 不需要启动 FastAPI 服务。
- 不需要调用方 import 项目内部 Python 模块。
- 不要求配置 PATH 或系统环境变量。
- 不暴露 provider、model、backend URL、分析师组合、输出语言等参数。
- 使用项目默认配置执行分析。
- 该入口是非交互式流程，不会出现菜单、确认提示或等待用户输入。
