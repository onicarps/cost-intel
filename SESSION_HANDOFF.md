# SESSION HANDOFF — Cost Intelligence

> **Last session:** June 3, 2026
> **Current state:** Phase 2 COMPLETE, Phase 3 ready to start
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
   pytest tests/ -q              # → 123 passed
   ```

3. **Update Linear issues** (mark Phase 2 as done):
   - Mark ONI-54 through ONI-59 as **Done**

4. **Kick off Phase 3** via individual droid exec:
   - Task 3.1 — `gate.py` cost gate
   - Task 3.2 — GitHub Actions example YAML
   - Task 3.3 — Slack webhook + SMTP email alerts

---

## Project Summary

**What:** `cost-intel` — standalone Python CLI that tracks AI spending at the task level, correlates with quality scores, produces cost-efficiency metrics.

**Value prop:** "No unified cost-quality metric in a CLI-native package."

**Repo:** https://github.com/onicarps/cost-intel (main branch, 15 commits)

---

## What Exists (Phase 1 + Phase 2 — Complete)

### Source Modules

| Module | Purpose | Phase |
|--------|---------|-------|
| `__init__.py` | `__version__ = "0.1.0"` | 1 |
| `__main__.py` | `python -m cost_intel` entry | 1 |
| `cli.py` | Typer app, all CLI commands | 1+2 |
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
| `migrations/001_initial.sql` | Phase 1 schema | 1 |
| `migrations/002_add_quality.sql` | Phase 2 schema (quality_scores + CPQP view) | 2 |

### CLI Commands (all working)

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
```

### Tests (123 passing, 0 lint errors)

| File | Tests | Coverage |
|------|-------|----------|
| test_config.py | 5 | Config loader, caching, eval weights |
| test_db.py | 12 | Schema, migrations, WAL, busy_timeout, contextmanager |
| test_duration.py | 12 | parse_window (d/h/w/bare/invalid) |
| test_estimate.py | 5 | Token estimation, cost prediction |
| test_ingest.py | 9 | Token extraction, JSONL ingest, error handling |
| test_migrations.py | 6 | Migration 002 quality + CPQP view |
| test_pricing.py | 10 | Upsert, historical, manual, refresh |
| test_quality.py | 13 | Import, combined_score, CSV, waste, CPQP |
| test_adapters.py | 3 | Eval Harness + Braintrust adapters |
| test_record.py | 11 | Recording, cost computation, getters |
| test_report.py | 9 | Summary, by-model/label/day, budget |
| test_cli_cpqp.py | 5 | CPQP CLI, waste-only, ratings |
| test_compare.py | 5 | Delta CPQP, empty filter |
| test_optimize.py | 9 | Routing, waste index, target CPQP, no-shadow |
| test_trends.py | 5 | Trend keys, CLI metric/cpqp |
| test_utils.py | 3 | now_iso, retry |

---

## What's Next: Phase 3 (CI/CD + Alerts)

**Approach:** Individual droid exec calls (small tasks, needs oversight).

### Tasks

| Task | Description | Key Files |
|------|-------------|-----------|
| 3.1 | Cost gate — `cost-intel gate --max-avg-cpqp 0.10 --window 7d` | `gate.py` |
| 3.2 | GitHub Actions example YAML | `.github/workflows/cost-gate.yml` |
| 3.3 | Budget alerts — Slack webhook + SMTP email | `alerts.py` |

### Phase 3 Gate
```bash
cost-intel gate --max-avg-cpqp 0.10 --window 7d  → exits 0 or 1
cost-intel alerts --channel slack --threshold 0.8  → sends when budget 80% exceeded
cost-intel alerts --channel email --threshold 0.8   → sends email alert
```

---

## Phase 4 (Multi-Agent) — After Phase 3

**Approach:** Two split Missions.
- **Mission A (OTel track):** Tasks 4.0+4.1+4.2 — migration 003, span ingestion, trace cost breakdown
- **Mission B (Optimization track):** Tasks 4.3+4.4 — prompt optimization, budget enforcement

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
| `SOUL.md` (profile root) | Mission + protocols |
| `AGENTS.md` (workspace) | Build rules + conventions |
| `PHASE1_COMPLETE.md` (workspace) | Phase 1 handoff details |
| `PHASE2_COMPLETE.md` (workspace) | Phase 2 handoff details |
| `mission-phase2.md` (workspace) | Factory Droid Phase 2 prompt |
| `plan.md` (workspace) | Full 4-phase plan (4297 lines) |
| `research/cost-intelligence/plan.md` (profile) | Original audited plan |
