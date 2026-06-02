# Factory Mission Prompt — Cost Intelligence Phase 1

## Mission
Implement Phase 1 (Cost-Only Foundation) of the Cost Intelligence project. Build a working Python CLI that tracks AI spending from the command line.

## Context
- **Project repo**: https://github.com/onicarps/cost-intel
- **Workspace**: `workspace/cost-intel/` in the cost-intel Hermes profile
- **AGENTS.md**: Read the workspace AGENTS.md first — it has the full project spec
- **Plan**: `workspace/cost-intel/plan.md` — 4297-line implementation plan, audit-approved, 0 open gaps
- **Linear issues**: ONI-43 through ONI-53 (Phase 1 milestone + 10 tasks)

## Phase 1 Tasks (in order)

### ONI-44: Task 1.0 — Config Loader + Shared Utilities
Create `src/cost_intel/config.py` and `src/cost_intel/utils.py`. Config reads `~/.cost-intel/config.yaml`. Utils has `retry()` and `now_iso()`. NOTE: `parse_window` lives in `duration.py` (Task 3.0/ONI-62) — do NOT duplicate it here.

### ONI-45: Task 1.1 — Project Scaffolding
Create `pyproject.toml` (hatchling, all dependencies, ruff config, entry point), `src/cost_intel/__init__.py` (`__version__ = "0.1.0"`), `__main__.py`, `cli.py` (Typer app with `--version` via `is_eager` callback), `tests/conftest.py`, `.env.example`, `.gitignore`, `scripts/bootstrap.sh`.

### ONI-46: Task 1.2 — Database Layer + Migration Framework
Create `src/cost_intel/db.py` (connection manager with contextmanager), `src/cost_intel/migration_runner.py` (numbered SQL migration runner), `src/cost_intel/migrations/001_initial.sql` (full schema with composite PK, indexes, all Phase 1 tables). Key: `PRAGMA busy_timeout=5000`, WAL mode, `with connect() as conn:` pattern.

### ONI-47: Task 1.3 — Model Pricing (Historical + Refresh)
Create `src/cost_intel/pricing.py` — fetch from OpenRouter API, store with composite PK `(model_id, effective_date)`, `is_current` flag. CLI: `cost-intel refresh-pricing`, `cost-intel pricing set/show`. Retry/backoff on API calls.

### ONI-48: Task 1.4 — Cost Recording
Create `src/cost_intel/record.py` — `record_run()` function storing `cost_runs` + `cost_run_calls` rows. Handles `cache_read_tokens`, `cache_write_tokens`, `raw_response`. CLI: `cost-intel record` with `--model`, `--input-tokens`, `--output-tokens`, `--cache-read`, `--cache-write`, `--cost`, `--label`, `--provider`.

### ONI-49: Task 1.5 — Reporting
Create `src/cost_intel/report.py` — aggregate views, time-window filtering. CLI: `cost-intel report` (summary), `cost-intel trends` (daily breakdown), `cost-intel export --format csv/json`. Uses `parse_window` from `duration.py`. Standard flags: `--last/-l`, `--days/-d`, `--window/-w`. Rich tables.

### ONI-50: Task 1.6 — Token Estimation
Create `src/cost_intel/estimate.py` — `tiktoken` pre-call estimation. CLI: `cost-intel estimate "your prompt here" --model gpt-4`.

### ONI-51: Task 1.7 — Ingest API Responses
Create `src/cost_intel/ingest.py` — JSONL ingestion with provider-specific cache token extraction. CLI: `cost-intel ingest-api-responses file.jsonl`. Handles OpenRouter, Anthropic, OpenAI response formats.

### ONI-52: Task 1.8 — Tests + CI + PyPI Publish
Write all unit tests (TDD — each module has `test_<module>.py`). Integration tests in `tests/integration/`. GitHub Actions CI workflow. `pyproject.toml` configured for PyPI. Verify `pip install cost-intel` works.

### ONI-53: Task 1.9 — Dogfood on Hermes Cron
Create `scripts/dogfood.sh` — record Hermes cron run costs daily. Document how to set up a cron job that uses `cost-intel record` to track Hermes's own AI spending.

### ONI-62: Task 3.0 — Shared Duration Parser (Phase 1 dependency)
Create `src/cost_intel/duration.py` — `parse_window("7d")` → 7. Tests in `tests/test_duration.py`. This is used by `--last`, `--window`, `--days` flags across multiple commands. Must be implemented early since Task 1.4+ depend on it.

## Rules
1. **TDD always** — write failing test FIRST, then implement, then verify
2. **Work task-by-task** in order (1.0 → 1.1 → 1.2 → ... → 1.9)
3. **Commit after every task** — `git add -A && git commit -m "type: description"`
4. **Branch naming**: `cost-intel/ONI-XX-description` (e.g., `cost-intel/ONI-44-config-loader`)
5. **Do NOT skip ahead** — earlier tasks set up modules/functions that later tasks import
6. **Do NOT implement Phase 2+ features** — this is Phase 1 only (cost-only, no quality scores)
7. **Run tests before every commit** — `pytest tests/ -v --cov=src`
8. **ruff check + ruff format** before every commit

## Phase 1 Gate (must pass before Phase 2)
- `pip install -e .` works in the workspace
- `cost-intel --version` prints `cost-intel 0.1.0`
- `cost-intel record --model gpt-4 --input-tokens 100 --output-tokens 50 --cost 0.003` stores a run
- `cost-intel report --days 7` shows the run in a Rich table
- `cost-intel trends` shows daily breakdown
- `cost-intel estimate "hello world" --model gpt-4` returns token count
- At least 80% test coverage
- All tests pass: `pytest tests/ -v --cov=src --cov-report=term-missing`
