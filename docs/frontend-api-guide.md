# 前端接口对接文档

## 说明
当前 Web API 基于 FastAPI 封装 TradingAgents 投研分析能力，采用“创建异步任务 + 查询任务状态/结果”的交互模式。首版无鉴权，任务状态保存在服务进程内存中，完整报告落盘到本地文件。

## 一、投研分析任务模块

### 1. 创建分析任务
- method: `POST`
- path: `/api/analysis-jobs`
- 功能说明: 创建异步投研分析任务，立即返回 `job_id`
- 请求参数:

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| ticker | string | 是 | 股票代码，例如 `AAPL` |
| trade_date | string | 是 | 分析日期，格式 `YYYY-MM-DD`，不能晚于当前日期 |
| selected_analysts | string[] | 否 | `market`、`social`、`news`、`fundamentals` |
| llm_provider | string | 否 | `openai`、`codex`、`anthropic`、`google`、`xai`、`openrouter`、`ollama` |
| deep_think_llm | string | 否 | 深度推理模型名称 |
| quick_think_llm | string | 否 | 快速推理模型名称 |
| backend_url | string | 否 | 自定义模型网关地址 |
| google_thinking_level | string | 否 | Google 模型 thinking 配置 |
| openai_reasoning_effort | string | 否 | OpenAI reasoning effort |
| codex_reasoning_effort | string | 否 | Codex reasoning effort |
| anthropic_effort | string | 否 | Anthropic effort |
| output_language | string | 否 | 报告输出语言 |
| max_debate_rounds | integer | 否 | 研究员辩论轮数，范围 1-10 |
| max_risk_discuss_rounds | integer | 否 | 风控辩论轮数，范围 1-10 |
| max_recur_limit | integer | 否 | 图执行递归上限，范围 1-300 |

- 响应字段:

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| job_id | string | 任务 ID |
| status | string | 初始状态，通常为 `pending` |

### 2. 查询分析任务状态/结果
- method: `GET`
- path: `/api/analysis-jobs/{job_id}`
- 功能说明: 查询任务状态、进度、最终分析结果和报告路径
- 请求参数:

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| job_id | string | 是 | 路径参数，创建任务时返回 |

- 响应字段:

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| job_id | string | 任务 ID |
| status | string | `pending` / `running` / `completed` / `failed` |
| progress | integer | 任务进度百分比 |
| request | object | 创建任务时提交的请求参数 |
| final_state | object/null | 完成后的结构化分析结果 |
| decision | string/null | 从 `final_trade_decision` 提取后的交易决策 |
| error_message | string/null | 失败原因 |
| report_path | string/null | 服务端落盘报告路径 |
| created_at | string | 任务创建时间 |
| started_at | string/null | 任务开始时间 |
| finished_at | string/null | 任务结束时间 |

`final_state` 主要字段:

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| company_of_interest | string | 标的代码 |
| trade_date | string | 分析日期 |
| market_report | string/null | 市场技术分析报告 |
| sentiment_report | string/null | 社交情绪分析报告 |
| news_report | string/null | 新闻分析报告 |
| fundamentals_report | string/null | 基本面分析报告 |
| investment_plan | string/null | 研究经理决策 |
| trader_investment_plan | string/null | 交易员方案 |
| final_trade_decision | string/null | 组合经理最终决策 |
| investment_debate_state | object | 多空研究员辩论过程 |
| risk_debate_state | object | 风控辩论过程 |

### 3. 下载完整 Markdown 报告
- method: `GET`
- path: `/api/analysis-jobs/{job_id}/report`
- 功能说明: 下载任务完成后生成的 `complete_report.md`
- 请求参数:

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| job_id | string | 是 | 路径参数 |

- 响应字段:

| 场景 | 响应 |
| --- | --- |
| 任务已完成 | 直接返回 Markdown 文件内容，`Content-Type: text/markdown; charset=utf-8` |
| 任务不存在 | `404` + `{"detail":"Analysis job not found"}` |
| 任务未完成/失败 | `409` + `{"detail":"Report for job ... is not ready..."}` |

## 二、元数据模块

### 4. 查询前端表单选项
- method: `GET`
- path: `/api/metadata/options`
- 功能说明: 返回可选分析师类型、LLM provider、模型列表和默认配置
- 请求参数: 无
- 响应字段:

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| analysts | string[] | 可选分析师列表 |
| llm_providers | string[] | 可选模型供应商列表 |
| models | object | 按 provider 和 `quick/deep` 分组的模型选项，元素格式为 `{label, value}` |
| default_config | object | 后端默认配置 |

## 三、前端对接建议
- 创建任务后轮询 `GET /api/analysis-jobs/{job_id}`，当 `status=completed` 后展示 `final_state` 并提供报告下载入口。
- 当 `status=failed` 时直接展示 `error_message`。
- `404/409/422` 统一按接口错误处理，其中 `422` 通常表示请求参数校验失败。
