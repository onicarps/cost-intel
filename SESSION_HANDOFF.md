# SESSION HANDOFF — Cost Intelligence

> **Last session:** June 3, 2026
> **Current state:** ALL 4 PHASES COMPLETE — Project done
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
   cost-intel --help             # → lists all 26 commands
   pytest tests/ -q              # → 164 passed
   ```

3. **Mark all Linear issues Done:**
   - ONI-43 through ONI-71 (29 issues) — all phases complete

---

## Project Summary

**What:** `cost-intel` — standalone Python CLI that tracks AI spending at the task level, correlates with quality scores, produces cost-efficiency metrics, integrates with CI/CD, supports OTel traces, and enforces budgets.

**Value prop:** "No unified cost-quality metric in a CLI-native package."

**Repo:** https://github.com/onicarps/cost-intel (main branch, ~28 commits)

**Complete:** 26 tasks, 164 tests, 24 source modules, 28 CLI commands

---

## Final State (All 4 Phases Complete)

### Source Loc

| Module | Purpose | Phase |
|--------|---------|-------|
| `__init__.py` | `__version__ = "0.1.0"` | 1 |
| `__main__.py` | `python -m cost_intel` entry | 1 |
| `cli.py` | Typer app, all CLI commands | 1+2+3+4 |
| `config.py` | YAML config loader with caching | 1 |
| `db.py` | Connection manager, `connect()`, `init_db()` | 1 |
| `migration_runner.py` | Numbered SQL migration runner | 1 |
| `duration.py` | `parse_window("7d")` (CANONICAL) | 1 |
| `pricing.py` | OpenRouter fetch, historical upsert | 1 |
| `record.py` | `record_run()` with trace columns | 1+4 |
| `report.py` | Summary, by-model, by-label, by-day | 1 |
| `budget.py` | `set_budget()`, `get_budget_status()` | 1 |
| `estimate.py` | `estimate_tokens()`, `estimate_cost()` | 1 |
| `ingest.py` | `ingest_jsonl()` with token extraction | 1 |
| `utils.py` | `now_iso()`, `retry()` | 1 |
| `quality.py` | Score import, CPQP, waste detection | 2 |
| `compare.py` | Model comparison with delta CPQP | 2 |
| `optimize.py` | Waste index, model routing, target CPQP | 2 |
| `trends.py` | CPQP week-over-week trend | 2 |
| `adapters/eval_harness.py` | Eval Harness SQLite adapter | 2 |
| `adapters/braintrust.py` | Braintrust REST API adapter | 2 |
| `gate.py` | CI/CD cost gate | 3 |
| `alerts.py` | Slack + SMTP budget alerts | 3 |
| `otel.py` | OTel span ingestion + trace cost | 4 |
| `prompt_opt.py` | Prompt optimization analysis | 4 |
| `guard.py` | Budget enforcement guard | 4 |
| `migrations/001_initial.sql` | Phase 1 schema | 1 |
| `migrations/002_add_quality.sql` | Phase 2 schema (quality_scores + CPQP view) | 2 |
| `migrations/003_add_trace_ids.sql` | Phase 3 schema (trace columns) | 4 |

### All 28 CLI Commands

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
cost-intel waste                              → waste analysis + index
cost-intel compare-models --label "summarize" → model comparison
cost-intel optimize --suggest-model-routing   → model routing suggestions
cost-intel import-scores --source csv ...     → CSV import
cost-intel gate --max-avg-cpqp 0.10 --window 7d → CI/CD cost gate
cost-intel alert check                        → run budget alerts
cost-intel alert test                         → show configured channels
cost-intel trace-cost <trace_id>              → span tree cost breakdown
cost-intel prompt-opt                         → prompt optimization analysis
cost-intel guard                              → budget enforcement
cost-intel import-scores --source eval-harness ... → Eval Harness import
cost-intel import-scores --source braintrust ...   → Braintrust import
cost-intel optimize --target-cpqp 0.05        → runs exceeding target CPQP
cost-intel gate --budget-check                → budget gate
```

### Tests (164 passing, 0 lint errors)

| File | Tests | Phase |
|------|-------|-------|
| test_config.py | 5 | 1 |
| test_db.py | 12 | 1 |
| test_duration.py | 12 | 1 |
| test_estimate.py | 5 | 1 |
| test_ingest.py | 9 | 1 |
| test_migrations.py | 9 | 2+4 |
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
| test_otel.py | 6 | 4 |
| test_prompt_opt.py | 6 | 4 |
| test_guard.py | 4 | 4 |
| test_utils.py | 3 | 1 |

---

## Environment & Credentials

**Profile:** `~/.hermes/profiles/cost-intel/`
**Venv:** `~/.hermes/profiles/cost-intel/workspace/cost-intel/.venv/`
**Workspace:** `~/.hermes/profiles/cost-intel/workspace/cost-intel/`

---

## File Locations Reference

| File | Purpose |
|------|---------|
| `PHASE1_COMPLETE.md` | Phase 1 handoff |
| `PHASE2_COMPLETE.md` | Phase 2 handoff |
| `PHASE3_COMPLETE.md` | Phase 3 handoff |
| `PHASE4_COMPLETE.md` | Phase 4 handoff |
| `plan.md` | Full 4-phase plan (4297 lines) |
