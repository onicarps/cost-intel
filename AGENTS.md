# AGENTS.md — Cost Intelligence

## Session Startup (MANDATORY)
1. Read SOUL.md (in profile root)
2. Read this file
3. Read SESSION_HANDOFF.md (in workspace root) — **start here for current state**
4. Read PHASE1_COMPLETE.md (in workspace root) — Phase 1 details
5. Read mission-phase2.md (in workspace root) — Phase 2 task specs
6. Check Linear for active tasks (project: Cost Intelligence, ONI-43..ONI-71)

## Project Status (June 3 2026)
**ALL 4 PHASES COMPLETE** — 26 tasks, 164 tests, pushed to GitHub.
See PHASE4_COMPLETE.md for full details.

**Project is DONE.** All phases implemented per the audit-approved plan.
- Migration 002: quality_scores table + cost_run_cpqp view with PERCENT_RANK()
- Quality score import adapters (Eval Harness, Braintrust, CSV)
- CPQP report, waste detection, model comparison, optimization

## Project
`cost-intel` — a standalone Python CLI for AI cost tracking and quality correlation.

## Mission
Build a CLI tool that tracks AI spending at the task level, correlates with quality scores, and produces cost-efficiency metrics. No tool currently bridges cost tracking and quality evaluation in a CLI-native package.

## Tech Stack
- Python 3.11+
- Typer + Rich (CLI + terminal output)
- sqlite3 stdlib (WAL mode, busy_timeout=5000)
- httpx (async HTTP for pricing API)
- Pydantic v2 (data validation)
- pyyaml (config loading)
- tiktoken (token estimation)
- hatchling (build backend)
- ruff (lint + format), pytest (test)

## Build Rules (NON-NEGOTIABLE)
- **TDD**: write failing test → run → implement → run → commit
- **Type hints everywhere** (mypy-compatible)
- **Google-style docstrings** for all public functions
- **ruff check + ruff format** before every commit
- **Commit after every task** (git add -A && git commit -m "type: description")
- **No API keys in source** — read from .env
- **`from typing import Optional`** in all modules using Optional

## Data Directory
`~/.cost-intel/` (override: `COST_INTEL_HOME`)
DB: `~/.cost-intel/cost-intel.db`
Config: `~/.cost-intel/config.yaml`

## File Organization
```
workspace/cost-intel/
├── src/cost_intel/           # Source package
│   ├── __init__.py           # __version__ = "0.1.0"
│   ├── __main__.py           # Entry point
│   ├── cli.py                # Typer app + sub-apps (ALL Phase 1 commands)
│   ├── config.py             # Config loader (reads ~/.cost-intel/config.yaml)
│   ├── db.py                 # Connection manager + migration runner
│   ├── migration_runner.py   # Numbered SQL migration runner
│   ├── migrations/           # Numbered SQL files
│   │   └── 001_initial.sql   # Phase 1 schema (COMPLETE)
│   ├── pricing.py            # OpenRouter fetch + historical store
│   ├── record.py             # Cost run recording (cache tokens + raw_response)
│   ├── report.py             # Aggregate views + time-window filtering
│   ├── budget.py             # Budget set/status subcommands
│   ├── estimate.py           # tiktoken pre-call estimation
│   ├── ingest.py             # JSONL ingestion with provider cache extraction
│   ├── duration.py           # parse_window("7d") → 7 (CANONICAL location)
│   ├── utils.py              # Shared utilities (retry, now_iso)
│   ├── quality.py            # [Phase 2] Score import + CPQP + waste detection
│   ├── optimize.py           # [Phase 2] Model routing + target CPQP
│   ├── compare.py            # [Phase 2] Model comparison with efficiency delta
│   ├── trends.py             # [Phase 2] CPQP trend analysis
│   ├── gate.py               # [Phase 3] CI/CD cost gates
│   ├── alerts.py             # [Phase 3] Slack webhook + SMTP email alerts
│   ├── otel.py               # [Phase 4] OpenTelemetry span ingestion + trace cost
│   ├── enforce.py            # [Phase 4] Budget enforcement / hard-stop
│   ├── prompt_opt.py         # [Phase 4] High-cost pattern analysis
│   └── adapters/             # [Phase 2] Quality score import adapters
│       ├── eval_harness.py   # [Phase 2] Eval Harness DB adapter
│       └── braintrust.py     # [Phase 2] Braintrust API adapter
├── tests/
│   ├── conftest.py           # Shared fixtures (tmp_db, tmp_cost_intel_home)
│   ├── test_*.py             # 10 test files, 77 tests (Phase 1 COMPLETE)
│   └── integration/          # Integration tests (empty — Phase 2+)
├── pyproject.toml            # hatchling build, dependencies, ruff config
├── .env.example              # Required env vars (no real values)
├── .github/workflows/ci.yml  # CI pipeline (ruff + pytest, Phase 1 COMPLETE)
├── scripts/
│   ├── bootstrap.sh          # One-command dev setup (executable)
│   └── dogfood.sh            # Dogfood: ingest + report (executable)
├── SESSION_HANDOFF.md        # **READ FIRST** — current state + next steps
├── PHASE1_COMPLETE.md        # Phase 1 implementation details
├── mission-phase2.md         # Factory Droid Phase 2 prompt
└── plan.md                   # Full 4-phase plan (4297 lines, audit-approved)
```

## Database Conventions
- Composite PK `(model_id, effective_date)` for historical pricing
- `is_current` flag on pricing rows
- Numbered SQL migrations: `001_initial.sql`, `002_add_quality.sql`, `003_add_traces.sql`
- `schema_version` table for migration tracking
- Views use `DROP VIEW IF EXISTS` + `CREATE VIEW` in migrations (not `IF NOT EXISTS`)
- `PRAGMA busy_timeout=5000` on all connections
- `PRAGMA journal_mode=WAL`
- Use `with connect() as conn:` contextmanager pattern
- **Standalone** — zero foreign keys to any other product

## Testing
- `pytest tests/ -v --cov=src --cov-report=term-missing`
- Coverage target: >90%
- Integration tests in `tests/integration/`
- No real API calls in CI (mock HTTP with pytest-httpx)
- Test file: `test_<module>.py` for each module
- `conftest.py` — shared fixtures (tmp_db, tmp_cost_intel_home)
- Each task: write failing test FIRST, then implement

## CLI Conventions
- Typer sub-apps for command groups (`budget`, `pricing`)
- Rich tables for reports
- Duration parser: `parse_window("7d")` → 7 (days). **Canonical location: `src/cost_intel/duration.py`**
- Standard flags: `--last/-l`, `--days/-d`, `--window/-w`
- `--version` flag via Typer `is_eager` callback

## Phase Gates
Each phase must pass validation before next phase starts:
- **Phase 1**: `pip install cost-intel` works, record + report work end-to-end, costs match invoices
- **Phase 2**: CPQP ordering matches intuition, division-by-zero guard works, percentile ratings displayed
- **Phase 3**: Gate exits 0/1 correctly, alerts trigger at right threshold
- **Phase 4**: OTel trace cost breakdown works, budget enforcement blocks when exceeded

## Credentials (in ~/.hermes/profiles/cost-intel/.env)
- `OPENROUTER_API_KEY`
- `LINEAR_API_KEY`
- `GITHUB_TOKEN`
- `FACTORY_API_KEY`

## Git
- Repo: https://github.com/onicarps/cost-intel
- Branch: main
- Branch naming: `cost-intel/ONI-XX-description`
- Commit style: `type: description` (feat:, fix:, test:, etc.)

## Linear Project
Cost Intelligence: ONI-43 through ONI-71 (29 issues, 4 phases)
Project ID: 55e43d66-e6a2-4108-9abe-fd97600aa79a

## Notion
https://www.notion.so/Cost-Intelligence-373e2527f3178147957ad4e1705278db

## Implementation Plan
See `plan.md` in this directory for full 4-phase implementation plan (4297 lines, audit-approved, 0 open gaps).
