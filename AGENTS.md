# Repository Guidelines

## Project Structure & Module Organization
`tradingagents/` contains the core multi-agent trading framework. Key subpackages are `agents/` for analyst, researcher, trader, and risk roles; `graph/` for LangGraph orchestration; `dataflows/` for market/news data adapters; and `llm_clients/` for provider-specific model wrappers and validation. `cli/` provides the Typer-based terminal interface and Rich UI helpers, with bundled text assets in `cli/static/`. Tests live in `tests/`, while top-level `main.py` and `test.py` are lightweight entry examples. Images and diagrams are stored in `assets/`.

## Build, Test, and Development Commands
Use Python 3.10+ and install locally. When running Python commands for this repository, always use the virtual environment interpreter at `.venv\Scripts\python.exe` instead of a system Python:
```bash
.venv\Scripts\python.exe -m pip install .
```
On Windows, prefer the repository PowerShell helpers for first-time setup:
```powershell
.\scripts\create_venv.ps1
.\scripts\install_deps.ps1
```
Run the interactive CLI:
```bash
tradingagents
.venv\Scripts\python.exe -m cli.main
```
Start the FastAPI backend with the maintained script or the packaged entry point:
```powershell
.\scripts\start_api.ps1
.\.venv\Scripts\tradingagents-api.exe
```
To bring up the local web stack during development, use:
```powershell
.\scripts\start_web_stack.ps1
```
Run tests with standard library discovery:
```bash
.venv\Scripts\python.exe -m unittest discover -s tests
```
Frontend work happens under `web-ui/` with Vite:
```bash
cd web-ui
npm run dev
npm run build
npm run test
```
For quick package smoke checks, run:
```bash
.venv\Scripts\python.exe main.py
```

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and uppercase constants such as `DEFAULT_CONFIG`. Prefer explicit imports from package modules (`from tradingagents.graph.trading_graph import TradingAgentsGraph`). Keep comments brief and focused on non-obvious behavior. No repository-wide formatter config is checked in, so match surrounding file style when editing.
For CLI, Web UI, and any other user-facing copy, default to Simplified Chinese so the product stays linguistically consistent. Only keep English for identifiers, data-source IDs, industry-standard abbreviations, or technical terms that would become less clear if translated.
Read and write project text files explicitly as UTF-8 whenever the tool allows specifying an encoding. On Windows, remember that terminal output may still use `GBK`/`CP936`, so any file inspection commands should prefer UTF-8-aware reads or switch the console to UTF-8 before judging whether content is actually garbled. Do not treat terminal mojibake alone as evidence that the file itself is mis-encoded.

## Testing Guidelines
Tests are written with `unittest` and named `tests/test_*.py`. Always run them with `.venv\Scripts\python.exe` so dependencies and interpreter behavior match the project environment. Keep test classes descriptive (`ModelValidationTests`) and test methods behavior-focused (`test_unknown_model_emits_warning_for_strict_provider`). Add regression tests for bug fixes in the package area you modify, especially model validation, ticker normalization, and API-key handling.
For the React/Vite frontend in `web-ui/`, run `npm run test` for component and config regressions when touching that surface.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commit prefixes such as `feat:`, `fix:`, `refactor:`, and `chore:`, sometimes with scopes like `fix(llm_clients): ...`. Use concise, imperative commit subjects and reference issue/PR numbers when relevant. Pull requests should describe the behavior change, list test commands run, call out config or API-key implications, and include CLI screenshots when UI output changes.

## Security & Configuration Tips
Never commit secrets. Copy `.env.example` to `.env` for local keys (`OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `ALPHA_VANTAGE_API_KEY`). Keep provider defaults and model names synchronized between `cli/` and `tradingagents/llm_clients/` when adding new models.
