# 股票分析 Skill 本地 CLI 接口实现方案

## 目标

为项目的股票分析能力提供一个供外部 skill 同机本地调用的接口。调用方通过子进程执行项目提供的 CLI，传入股票代码，项目使用默认配置完成分析，并返回最终结论的 Markdown 文本。

该接口面向机器调用，不替代现有交互式 CLI，也不修改现有命令行为。

## 范围

首期只接入股票分析能力：

```powershell
E:\document\tradingAgents\.venv\Scripts\python.exe E:\document\tradingAgents\skill-cli\tradingagents_skill.py stock-analysis AAPL
```

后续可以在同一接口层扩展市场监控等能力：

```powershell
E:\document\tradingAgents\.venv\Scripts\python.exe E:\document\tradingAgents\skill-cli\tradingagents_skill.py market-monitor
```

## 目录要求

### 1. 根目录新增 CLI 脚本目录

在项目根目录新建独立目录存放供 skill 调用的 CLI 脚本，例如：

```text
skill-cli/
  tradingagents_skill.py
```

该目录只放面向外部 skill / 子进程调用的薄封装脚本，不承载核心业务逻辑。

设计约束：

- 不修改现有交互式 CLI 命令。
- 不要求调用方配置环境变量或 PATH。
- 不依赖调用方当前工作目录，skill 文档和示例命令必须使用项目解释器和脚本的完整路径。
- 调用方可以直接使用项目虚拟环境解释器执行脚本。
- CLI 脚本内部复用项目现有股票分析能力。
- CLI 脚本保持非交互式，不出现菜单、确认提示或需要用户输入的流程。

### 2. 根目录新增 skills 目录

在项目根目录新建 `skills` 文件夹，并新增 `tradingagents-stock-analysis` skill：

```text
skills/
  tradingagents-stock-analysis/
    SKILL.md
```

`tradingagents-stock-analysis` 负责描述外部 skill 如何调用本项目的本地 CLI，包括命令格式、输入、输出、错误处理和示例。

## 推荐命令契约

股票分析命令：

```powershell
E:\document\tradingAgents\.venv\Scripts\python.exe E:\document\tradingAgents\skill-cli\tradingagents_skill.py stock-analysis <ticker>
```

示例：

```powershell
E:\document\tradingAgents\.venv\Scripts\python.exe E:\document\tradingAgents\skill-cli\tradingagents_skill.py stock-analysis AAPL
```

参数：

- `<ticker>`：必填，待分析股票代码。

首期不暴露以下参数：

- provider
- model
- backend URL
- 分析师组合
- 输出语言
- 交互式配置项

这些配置均使用项目默认配置。

## 输出契约

### stdout

成功时，`stdout` 只输出最终结论 Markdown 文本。

外部 skill 可以直接读取子进程标准输出，并将其作为分析结果使用。

### stderr

进度、日志、告警和错误说明输出到 `stderr`，避免污染 Markdown 结果。

### 退出码

建议使用稳定退出码：

```text
0  成功，stdout 为最终 Markdown
2  参数错误，例如缺少 ticker 或 ticker 格式非法
3  环境或配置错误，例如依赖未安装、默认配置不可用
4  分析运行失败，例如数据源、模型调用或图执行失败
```

## 股票代码校验

CLI 层应对 `<ticker>` 做最小白名单校验，避免路径穿越、命令注入或异常字符进入后续流程。

建议首期允许：

```text
A-Z
0-9
.
-
_
```

并限制最大长度，例如 32 个字符。

校验失败时：

- `stderr` 输出错误原因。
- 退出码为 `2`。
- `stdout` 不输出内容。

## 内部调用方式

`skill-cli/tradingagents_skill.py` 只作为薄封装层：

1. 解析命令和参数。
2. 校验股票代码。
3. 加载项目默认配置。
4. 调用现有股票分析执行逻辑。
5. 提取最终结论 Markdown。
6. 将 Markdown 写入 `stdout`。
7. 将日志和错误写入 `stderr`。

核心股票分析逻辑仍保留在现有模块中，避免在 skill CLI 中复制业务流程。

## 后续扩展方式

采用一级能力名扩展：

```text
stock-analysis
market-monitor
```

未来新增市场监控时，可以复用同一个入口脚本：

```powershell
E:\document\tradingAgents\.venv\Scripts\python.exe E:\document\tradingAgents\skill-cli\tradingagents_skill.py market-monitor
```

市场监控能力接入时，也应遵守同样的机器调用契约：

- 非交互式。
- stdout 只输出最终 Markdown 或约定结果。
- stderr 输出日志和错误。
- 使用稳定退出码。
- 不影响现有 Web/API/CLI 行为。

## skill 文档要求

`skills/tradingagents-stock-analysis/SKILL.md` 应至少包含：

- skill 用途说明。
- 本地调用命令。
- 必填输入：股票代码。
- 输出说明：最终结论 Markdown。
- 失败时如何读取 `stderr` 和退出码。
- 示例调用。
- 约束：只使用项目默认配置，不要求启动 API 服务。

## 非目标

首期不做以下内容：

- 不提供 HTTP API。
- 不改造现有交互式 CLI。
- 不新增模型/provider 参数。
- 不让外部 skill import 项目内部 Python 模块。
- 不要求注册系统环境变量。
- 不要求把 `.venv\Scripts` 加入 PATH。

## 验收标准

完成实现后，应满足：

1. 项目根目录存在 `skill-cli` 目录，并包含股票分析 CLI 脚本。
2. 项目根目录存在 `skills/tradingagents-stock-analysis/SKILL.md`。
3. 外部调用方可以通过子进程执行：

   ```powershell
   E:\document\tradingAgents\.venv\Scripts\python.exe E:\document\tradingAgents\skill-cli\tradingagents_skill.py stock-analysis AAPL
   ```

4. 成功时 `stdout` 只包含最终结论 Markdown。
5. 进度和错误信息不混入 `stdout`。
6. 不修改现有 CLI 命令的调用方式和输出行为。
7. 后续市场监控能力可以在同一 CLI 入口下新增子命令。
