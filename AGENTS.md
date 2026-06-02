# AGENTS.md — Cost Intelligence Project

## Project
`cost-intel` — a standalone Python CLI for AI cost tracking and quality correlation.

## Mission
Build a CLI tool that tracks AI spending at the task level, correlates with quality scores, and produces cost-efficiency metrics. No tool currently bridges cost tracking and quality evaluation in a CLI-native package.

## Tech Stack
- Python 3.11+
- Typer + Rich (CLI)
- sqlite3 stdlib (WAL mode)
- httpx, Pydantic v2, pyyaml, tiktoken
- hatchling (build), ruff (lint), pytest (test)

## Conventions
- TDD: write failing test → implement → verify → commit
- Type hints everywhere
- Google-style docstrings
- ruff check + ruff format before every commit
- `from typing import Optional` in all modules using Optional

## Data Directory
`~/.cost-intel/` (override: `COST_INTEL_HOME`)
DB: `~/.cost-intel/cost-intel.db`

## Database
- Composite PK `(model_id, effective_date)` for historical pricing
- Numbered SQL migrations in `src/cost_intel/migrations/`
- `schema_version` table for tracking
- `PRAGMA busy_timeout=5000` on connections
- Use `with connect() as conn:` contextmanager

## Testing
- `pytest tests/ -v --cov=src`
- Coverage target: >90%
- Mock HTTP in tests (pytest-httpx)

## Duration Parser
Canonical: `src/cost_intel/duration.py` — `parse_window("7d")` → 7
Used by: `--last`, `--window`, `--days` flags

## Phase Structure
- Phase 1: Cost-only foundation (CLI + DB + pricing + reporting)
- Phase 2: Quality correlation (CPQP + waste detection + adapters)
- Phase 3: CI/CD gates + alerts
- Phase 4: Multi-agent (OTel) + advanced features

## Credentials
Read from .env: OPENROUTER_API_KEY, FACTORY_API_KEY

## Linear Project
Cost Intelligence: ONI-43 through ONI-71

## Implementation Plan
See `research/cost-intel/plan.md` for full 4-phase implementation plan (4000+ lines, audit-approved).
