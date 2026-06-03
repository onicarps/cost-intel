# SESSION HANDOFF — Cost Intelligence

> **Last session:** June 3, 2026
> **Current state:** Phase 3 COMPLETE, Phase 4 ready to start
> **Read this file first** if you're continuing this project in a new session

---

## Immediate Next Steps (do these first)

1. **Activate the venv:**
   ```bash
   cd ~/.hermes/profiles/cost-intel/workspace/cost-intel
   source .venv/bin/activate
   ```

2. **Verify everything works:**
   ```bash
   cost-intel --version          # → 0.1.0
   cost-intel --help             # → lists all commands
   pytest tests/ -q              # → 145 passed
   ```

3. **Update Linear issues** (mark Phase 3 as done):
   - Mark ONI-63, ONI-64, ONI-65 as **Done**

4. **Kick off Phase 4** via two split Factory Missions:
   - **Mission A (OTel track):** Tasks 4.0+4.1+4.2 — migration 003, span ingestion, trace cost breakdown
   - **Mission B (Optimization track):** Tasks 4.3+4.4 — prompt optimization, budget enforcement

---

## Project Summary

**What:** `cost-intel` — standalone Python CLI that tracks AI spending at the task level, correlates with quality scores, produces cost-efficiency metrics, and integrates with CI/CD.

**Value prop:** "No unified cost-quality metric in a CLI-native package."

**Repo:** https://github.com/onicarps/cost-intel (main branch, 21 commits)

---

## What Exists (Phases 1-3 Complete)

### Source Modules (24 files)

| Module | Purpose | Phase |
|--------|---------|-------|
| `__init__.py` | `__version__ = "0.1.0"` | 1 |
| `__main__.py` | `python -m cost_intel` entry | 1 |
| `cli.py` | Typer app, all CLI commands | 1+2+3 |
| `config.py` | YAML config loader with caching | 1 |
| `db.py` | Connection manager, `connect()` contextmanager, `init_db()` | 1 |
| `migration_runner.py` | Numbered SQL migration runner | 1 |
| `duration.py` | `parse_window("7d")` → 7 (CANONICAL) | 1 |
| `pricing.py` | OpenRouter fetch, historical upsert, refresh CLI | 1 |
| `record.py` | `record_run()`, `get_run()`, `get_run_calls()` | 1 |
| `report.py` | Summary, by-model, by-label, by-day with time-window | 1 |
| `budget.py` | `set_budget()`, `get_budget_status()` | 1 |
| `estimate.py` | `estimate_tokens()`, `estimate_cost()` (tiktoken) | 1 |
| `ingest.py` | `ingest_jsonl()` with provider token extraction | 1 |
| `utils.py` | `now_iso()`, `retry()` | 1 |
| `quality.py` | Score import, CPQP, waste detection | 2 |
| `compare.py` | Model comparison with delta CPQP | 2 |
| `optimize.py` | Waste index, model routing, target CPQP | 2 |
| `trends.py` | CPQP week-over-week trend | 2 |
| `adapters/eval_harness.py` | Eval Harness SQLite adapter | 2 |
| `adapters/braintrust.py` | Braintrust REST API adapter | 2 |
| `gate.py` | CI/CD cost gate (CPQP/waste-index/budget) | 3 |
| `alerts.py` | Slack + SMTP budget alerts | 3 |
| `migrations/001_initial.sql` | Phase 1 schema | 1 |
| `migrations/002_add_quality.sql` | Phase 2 schema | 2 |

### All CLI Commands

```
cost-intel --version                          → 0.1.0
cost-intel record --model M -i 100 -o 50      → record a run
cost-intel report --last 7d --by-model        → cost report
cost-intel trends --last 30d                  → daily spending trends
cost-intel trends --metric cpqp --days 14     → CPQP trend
cost-intel export --format csv --last 7d      → CSV export
cost-intel budget set --monthly 500           → set budget
cost-intel budget status                      → show status
cost-intel refresh-pricing                    → fetch pricing
cost-intel pricing set/show --model M         → manual pricing
cost-intel estimate "text" --model gpt-4      → token estimation
cost-intel ingest-api-responses file.jsonl    → ingest JSONL
cost-intel cpqp --last 30d                    → CPQP report with ratings
cost-intel cpqp --waste-only                  → D/F rated runs only
cost-intel waste                              → waste analysis + index
cost-intel compare-models --label "summarization" → model comparison
cost-intel optimize --suggest-model-routing   → model routing suggestions
cost-intel optimize --target-cpqp 0.05        → runs exceeding target
cost-intel import-scores --source csv ...     → CSV import
cost-intel import-scores --source eval-harness ... → Eval Harness import
cost-intel import-scores --source braintrust ...   → Braintrust import
cost-intel gate --max-avg-cpqp 0.10 --window 7d → CI/CD cost gate
cost-intel gate --max-waste-index 0.20        → waste index gate
cost-intel gate --budget-check                → budget gate
cost-intel gate --format json                 → JSON output
cost-intel alert check                        → run budget alerts
cost-intel alert test                         → show configured channels
```

### Tests (145 passing, 0 lint errors)

| File | Tests | Phase |
|------|-------|-------|
| test_config.py | 5 | 1 |
| test_db.py | 12 | 1 |
| test_duration.py | 12 | 1 |
| test_estimate.py | 5 | 1 |
| test_ingest.py | 9 | 1 |
| test_migrations.py | 6 | 2 |
| test_pricing.py | 10 | 1 |
| test_quality.py | 13 | 2 |
| test_adapters.py | 3 | 2 |
| test_record.py | 11 | 1 |
| test_report.py | 9 | 1 |
| test_cli_cpqp.py | 5 | 2 |
| test_compare.py | 5 | 2 |
| test_optimize.py | 9 | 2 |
| test_trends.py | 5 | 2 |
| test_gate.py | 13 | 3 |
| test_alerts.py | 9 | 3 |
| test_utils.py | 3 | 1 (includes gate window parsing) |

---

## What's Next: Phase 4 (Multi-Agent + Advanced)

**Approach:** Two split Missions.

### Mission A — OTel Track (Tasks 4.0-4.2)

| Task | Description | Key Files |
|------|-------------|-----------|
| 4.0 | Migration 003: trace_id, span_id, parent_span_id columns on cost_runs | `migrations/003_add_traces.sql` |
| 4.1 | OTel span ingestion from JSON/OTLP | `otel.py` |
| 4.2 | Trace cost breakdown (total cost per trace, per-span cost attribution) | `otel.py` CLI commands |

### Mission B — Optimization Track (Tasks 4.3-4.4)

| Task | Description | Key Files |
|------|-------------|-----------|
| 4.3 | Prompt optimization: identify high-cost patterns, suggest shorter prompts | `prompt_opt.py` |
| 4.4 | Budget enforcement: hard-stop when budget exceeded (middleware pattern) | `enforce.py` |

### Phase 4 Gate
```bash
cost-intel ingest-otel trace.json              → ingest OTel spans
cost-intel trace-cost --trace-id abc123        → total trace cost breakdown
cost-intel prompt-analyze --last 30d           → high-cost prompt patterns
cost-intel enforce --monthly 100              → blocks when budget exceeded
```

---

## Environment & Credentials

**Profile:** `~/.hermes/profiles/cost-intel/`
**Venv:** `~/.hermes/profiles/cost-intel/workspace/cost-intel/.venv/`
**Workspace:** `~/.hermes/profiles/cost-intel/workspace/cost-intel/`

**Activate before working:**
```bash
cd ~/.hermes/profiles/cost-intel/workspace/cost-intel
source .venv/bin/activate
```

---

## Important Constraints

1. **TDD always** — write failing test FIRST, then implement
2. **No API keys in source** — read from `.env`
3. **`from typing import Optional`** in every module using Optional
4. **ruff check + ruff format** before every commit
5. **Migration-first schema changes** — never use ALTER TABLE outside migrations
6. **Percentile-based ratings** — never hardcode dollar thresholds
7. **Standalone** — zero foreign keys to any other product
8. **Views use DROP+CREATE** — never `CREATE VIEW IF NOT EXISTS`

---

## File Locations Reference

| File | Purpose |
|------|---------|
| `PHASE1_COMPLETE.md` | Phase 1 handoff |
| `PHASE2_COMPLETE.md` | Phase 2 handoff |
| `PHASE3_COMPLETE.md` | Phase 3 handoff |
| `plan.md` | Full 4-phase plan (4297 lines) |
| `mission-phase2.md` | Factory Droid Phase 2 prompt |
