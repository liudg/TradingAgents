# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup and development commands

### Python environment
- This repo targets Python 3.10+.
- On Windows, prefer the project virtualenv interpreter instead of system Python: `.venv\Scripts\python.exe`.
- Create the virtualenv:
  - `powershell -File .\scripts\create_venv.ps1`
- Install the package and dependencies into `.venv`:
  - `powershell -File .\scripts\install_deps.ps1`
  - Equivalent direct command: `.venv\Scripts\python.exe -m pip install .`

### Main runtime entrypoints
- Interactive CLI:
  - `.\.venv\Scripts\tradingagents.exe`
  - `.venv\Scripts\python.exe -m cli.main`
- FastAPI backend:
  - `powershell -File .\scripts\start_api.ps1`
  - `.venv\Scripts\tradingagents-api.exe`
  - With custom host/port and reload: `powershell -File .\scripts\start_api.ps1 -BindHost 127.0.0.1 -Port 8000 -Reload`
- Combined backend + frontend launcher:
  - `powershell -File .\scripts\start_web_stack.ps1`
  - With custom host/API port/web port and reload: `powershell -File .\scripts\start_web_stack.ps1 -BindHost 127.0.0.1 -ApiPort 8000 -WebPort 5173 -Reload`
  - If `web-ui/node_modules` is missing, this script installs frontend dependencies before launching.
  - If `scripts\sync_codex_to_cliproxy.ps1` exists, it also tries to refresh local Codex auth and restart CLIProxyAPI before starting the backend and frontend; startup continues if that step fails.
- Local Codex/CLIProxy sync helper:
  - `powershell -File .\scripts\sync_codex_to_cliproxy.ps1`
- Package smoke test/example run:
  - `.venv\Scripts\python.exe main.py`

### Frontend (`web-ui/`)
- Install deps:
  - `cd web-ui && npm install`
- Start dev server:
  - `cd web-ui && npm run dev`
- Build:
  - `cd web-ui && npm run build`
- Run frontend tests:
  - `cd web-ui && npm run test`
- Preview production build:
  - `cd web-ui && npm run preview`

### Tests
- The Python test suite uses `unittest`, not `pytest`.
- Run all Python tests:
  - `.venv\Scripts\python.exe -m unittest discover -s tests`
- Run a single test file:
  - `.venv\Scripts\python.exe -m unittest tests.test_web_api`
- Run a single test class:
  - `.venv\Scripts\python.exe -m unittest tests.test_market_monitor_api.MarketMonitorRunApiTests`
- Run a single test method:
  - `.venv\Scripts\python.exe -m unittest tests.test_market_monitor_api.MarketMonitorRunApiTests.test_run_api_exposes_pipeline_resources`

### Docker
- Main container flow:
  - `docker compose run --rm tradingagents`
- Ollama profile:
  - `docker compose --profile ollama run --rm tradingagents-ollama`

### Notes on linting/type checks
- No repo-level Python lint/format command is currently checked in.
- For the frontend, `npm run build` performs the TypeScript build used in practice for validation.

## Repository architecture

### Big picture
TradingAgents is a LangGraph-based multi-agent trading research system with three user-facing surfaces:
- terminal CLI in `cli/`
- HTTP API in `tradingagents/web/api/`
- React web UI in `web-ui/`

The core execution engine lives in `tradingagents/` and is shared by CLI runs, API analysis jobs, and backtesting.

### Core execution flow
The main orchestrator is `tradingagents/graph/trading_graph.py`.
- `TradingAgentsGraph` builds provider-specific LLM clients from config, initializes long-lived memories, creates tool nodes, and compiles the LangGraph workflow.
- `propagate(company_name, trade_date)` runs the graph and returns both the final state and a processed trade signal.
- Final graph state is logged and later persisted into structured markdown reports.

The workflow itself is assembled in `tradingagents/graph/setup.py`.
Execution order is:
1. selected analysts run first (`market`, `social`, `news`, `fundamentals`)
2. bull/bear researchers debate
3. research manager produces the investment judgment
4. trader creates the trading plan
5. aggressive / conservative / neutral risk agents debate
6. portfolio manager emits the final decision

Conditional transitions for repeated debate/tool loops live in `tradingagents/graph/conditional_logic.py` and are enforced during graph execution.

### Agent and data layers
- `tradingagents/agents/`: agent role implementations and prompts for analysts, researchers, trader, risk, and managers.
- `tradingagents/dataflows/`: market/news/fundamental data access and vendor routing.
- `tradingagents/agents/utils/agent_utils.py`: abstract tool functions exposed to LangGraph tool nodes.
- `tradingagents/llm_clients/`: provider abstraction and model catalog for OpenAI, Codex, Anthropic, Google, xAI, OpenRouter, and Ollama.

A useful implementation detail: tool nodes are organized by analyst domain rather than by provider. Provider selection happens underneath the tool layer via config.

### Configuration behavior
Default runtime settings live in `tradingagents/default_config.py`.
Important repo-specific defaults:
- default LLM provider is `codex`
- default deep/quick models are `gpt-5.4` and `gpt-5.4-mini`
- default backend URL is `http://127.0.0.1:8317/v1`
- user-facing output language defaults to `Chinese`
- internal debate/reasoning remains English-oriented for model quality

If you change provider/model support, keep `tradingagents/default_config.py`, `tradingagents/llm_clients/model_catalog.py`, and the API metadata returned by `tradingagents/web/api/app.py` aligned.

### Reporting and persisted outputs
Structured report writing lives in `tradingagents/reporting.py`.
Completed reports are written as:
- `results/<ticker>/<trade-date>/<job-id>/reports/complete_report.md`
- with per-stage subfolders such as `1_analysts/`, `2_research/`, `3_trading/`, `4_risk/`, `5_portfolio/`

The API-side analysis manager in `tradingagents/web/analysis/manager.py` uses the same layout and also writes `message_tool.log` alongside each job run.

### Web/API architecture
`tradingagents/web/api/app.py` is the FastAPI entrypoint.
It exposes four major capability groups:
- analysis jobs
- historical reports
- backtest jobs / historical backtests
- market monitor runs

#### Analysis jobs
`tradingagents/web/analysis/manager.py` manages asynchronous analysis runs.
- Jobs are stored in memory and executed in a thread pool.
- It instantiates `TradingAgentsGraph`, streams graph chunks for progress logging, persists the final report, and exposes logs/report metadata to the API.

#### Backtesting
Backtesting lives under `tradingagents/web/backtest/`.
It replays multiple dates by repeatedly calling `TradingAgentsGraph.propagate()` and can persist reflection/memory artifacts based on outcomes.

#### Market monitor
The market monitor is a separate pipeline under `tradingagents/web/market_monitor/`.
`service.py` runs a staged asynchronous workflow:
1. build input bundle
2. collect search slots
3. build fact sheet
4. generate judgment cards
5. produce execution summary

This subsystem has its own run store, prompt capture store, evidence/log endpoints, and dedicated tests.

### Frontend integration
The React frontend in `web-ui/` talks to the FastAPI backend through `/api`.
During local development, the Vite dev server proxies `/api` to `http://127.0.0.1:8000`.
The frontend is primarily a control surface for asynchronous backend jobs rather than a separate business-logic implementation.

## Project-specific conventions and gotchas
- Prefer Simplified Chinese for CLI, web UI, and other user-facing copy. Keep English for identifiers, model/provider IDs, and technical terms when translation would reduce clarity.
- Read and write repository text files as UTF-8. On Windows, avoid assuming terminal mojibake means the file encoding is wrong.
- Tests are `unittest`-based and follow `tests/test_*.py` naming.
- When changing model/provider support, check both the CLI/API-facing configuration surfaces and the backend provider catalog rather than updating only one layer.
- The repo already includes `AGENTS.md`; its useful project-specific guidance has been folded into this file.