# Repository Guidelines

## Project Structure & Module Organization
`tradingagents/` contains the core multi-agent trading framework. Key subpackages are `agents/` for analyst, researcher, trader, and risk roles; `graph/` for LangGraph orchestration; `dataflows/` for market/news data adapters; and `llm_clients/` for provider-specific model wrappers and validation. `cli/` provides the Typer-based terminal interface and Rich UI helpers, with bundled text assets in `cli/static/`. Tests live in `tests/`, while top-level `main.py` and `test.py` are lightweight entry examples. Images and diagrams are stored in `assets/`.

## Build, Test, and Development Commands
Use Python 3.10+ and install locally:
```bash
pip install .
```
Run the interactive CLI:
```bash
tradingagents
python -m cli.main
```
Run tests with standard library discovery:
```bash
python -m unittest discover -s tests
```
For quick package smoke checks, run:
```bash
python main.py
```

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, `snake_case` for functions and modules, `PascalCase` for classes, and uppercase constants such as `DEFAULT_CONFIG`. Prefer explicit imports from package modules (`from tradingagents.graph.trading_graph import TradingAgentsGraph`). Keep comments brief and focused on non-obvious behavior. No repository-wide formatter config is checked in, so match surrounding file style when editing.

## Testing Guidelines
Tests are written with `unittest` and named `tests/test_*.py`. Keep test classes descriptive (`ModelValidationTests`) and test methods behavior-focused (`test_unknown_model_emits_warning_for_strict_provider`). Add regression tests for bug fixes in the package area you modify, especially model validation, ticker normalization, and API-key handling.

## Commit & Pull Request Guidelines
Recent history follows Conventional Commit prefixes such as `feat:`, `fix:`, `refactor:`, and `chore:`, sometimes with scopes like `fix(llm_clients): ...`. Use concise, imperative commit subjects and reference issue/PR numbers when relevant. Pull requests should describe the behavior change, list test commands run, call out config or API-key implications, and include CLI screenshots when UI output changes.

## Security & Configuration Tips
Never commit secrets. Copy `.env.example` to `.env` for local keys (`OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `ALPHA_VANTAGE_API_KEY`). Keep provider defaults and model names synchronized between `cli/` and `tradingagents/llm_clients/` when adding new models.
