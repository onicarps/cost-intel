# Cost Intelligence — Phase 1 Implementation Complete

> **Date:** June 2-3, 2026
> **Status:** Phase 1 (Cost-Only Foundation) — ALL 12 tasks complete
> **Tests:** 77 passing, ruff clean, 0 lint errors
> **GitHub:** https://github.com/onicarps/cost-intel (7 commits on main)

---

## What Was Built

A standalone Python CLI (`cost-intel`) that tracks AI spending from the command line.
No quality data needed — purely cost-only layer (Phase 1).

### Source Modules Created

| Module | Purpose |
|--------|---------|
| `src/cost_intel/__init__.py` | `__version__ = "0.1.0"` |
| `src/cost_intel/__main__.py` | `python -m cost_intel` entry |
| `src/cost_intel/cli.py` | Typer app with all CLI commands |
| `src/cost_intel/config.py` | YAML config loader with caching |
| `src/cost_intel/utils.py` | `now_iso()`, `retry()` with exponential backoff |
| `src/cost_intel/duration.py` | `parse_window("7d")` → 7 (CANONICAL location) |
| `src/cost_intel/db.py` | Connection manager + `connect()` contextmanager + `init_db()` |
| `src/cost_intel/migration_runner.py` | Numbered SQL migration runner |
| `src/cost_intel/migrations/001_initial.sql` | Full Phase 1 schema |
| `src/cost_intel/pricing.py` | OpenRouter fetch, upsert (same-day update vs cross-date insert), get, manual |
| `src/cost_intel/record.py` | `record_run()`, `get_run()`, `get_run_calls()` |
| `src/cost_intel/report.py` | `report_summary()`, `report_by_model()`, `report_by_label()`, `report_by_day()` |
| `src/cost_intel/budget.py` | `set_budget()`, `get_budget_status()` |
| `src/cost_intel/estimate.py` | `estimate_tokens()`, `estimate_cost()` (tiktoken) |
| `src/cost_intel/ingest.py` | `ingest_jsonl()` with provider token extraction |

### CLI Commands Working

```
cost-intel --version                          → cost-intel 0.1.0
cost-intel record --model M -i 100 -o 50      → record a cost run
cost-intel report --last 7d --by-model        → cost report with tables
cost-intel trends --last 30d                  → daily spending trends
cost-intel export --format csv --last 7d      → CSV export
cost-intel budget set --monthly 500           → set budget
cost-intel budget status                      → show budget status
cost-intel refresh-pricing                    → fetch from OpenRouter API
cost-intel pricing set/show --model M         → manual pricing
cost-intel estimate "hello" --model gpt-4     → token/cost estimation
cost-intel ingest-api-responses file.jsonl    → ingest JSONL
```

---

## Known Issues / Bugs Found During Implementation

1. **OpenRouter pricing math**: API returns per-million-token pricing. Must multiply by `1_000_000` to get per-1K-token pricing (not `1_000`). Fixed in `refresh_all_pricing()`.

2. **Same-day upsert DELETE+INSERT**: Using `INSERT OR REPLACE` with composite PK `(model_id, effective_date)` deleted the old row entirely, so `is_current=0` historical rows were lost. Fixed with conditional logic: same-day → UPDATE in place, different day → mark old `is_current=0` + INSERT new.

3. **SQLite datetime comparison**: ISO timestamps with timezone offsets (`2025-01-01T00:00:00+00:00`) don't compare correctly with SQLite's `datetime('now', '-N days')` which returns `'YYYY-MM-DD HH:MM:SS'` format. Fixed test to use `'YYYY-MM-DD HH:MM:SS'` format for manually inserted timestamps.

4. **`dict` params vs positional `?`**: Report `_days_filter()` passed a dict to `conn.execute()` but SQL used `?` positional placeholders. Fixed to return `list` instead of `dict`.

---

## Test Coverage (77 tests)

| Test File | Tests | What's Covered |
|-----------|-------|----------------|
| `test_config.py` | 5 | Config loader (no file, reads YAML, caches, eval weights) |
| `test_utils.py` | 3 | now_iso, retry (success, retries, raises) |
| `test_duration.py` | 12 | parse_window (d/h/w/bare int/whitespace/case/invalid) |
| `test_db.py` | 12 | Schema creation, migrations, composite PK, WAL, busy_timeout, foreign_keys, contextmanager commit/rollback |
| `test_pricing.py` | 10 | Upsert, update preserves old row, same-day update, noop, cache pricing, historical pricing, manual pricing, refresh insert/skip |
| `test_record.py` | 11 | Basic record, cost computation, unknown model, cache tokens, raw_response truncation, run_type, label, latency, get_run, get_run_calls |
| `test_report.py` | 9 | Summary empty/with-runs/time-window, by-model, by-label, by-day, budget set/status/spending |
| `test_estimate.py` | 5 | Token estimation (basic, empty, longer=text, cost with pricing/unknown) |
| `test_ingest.py` | 9 | Token extraction (OpenRouter/Anthropic/OpenAI/unknown), JSONL ingest (basic, skip invalid, label, nonexistent file) |

---

## Remaining Phases

### Phase 2: Quality Correlation (Weeks 4-6)
Tasks 2.0-2.5 — Quality scores, CPQP metric, waste detection, model comparison

Key migration needed: `002_add_quality.sql` — adds `quality_scores` table + `cost_run_cpqp` view with `PERCENT_RANK()` for A/B/C/D/F ratings.

### Phase 3: CI/CD + Alerts (Weeks 7-9)
Tasks 3.1-3.3 — Cost gate, GitHub Actions example, Slack/email alerts

### Phase 4: Multi-Agent + Advanced (Weeks 10-12)
Tasks 4.0-4.4 — OTel span ingestion, trace cost breakdown, prompt optimization, budget enforcement

Migration needed: `003_add_traces.sql` — adds `trace_id`, `span_id`, `parent_span_id` to `cost_runs`.

---

## Key Files for Next Session

- **Plan:** `research/cost-intelligence/plan.md` (4297 lines, audit-approved)
- **AGENTS.md:** `workspace/cost-intel/AGENTS.md` (full project spec + file tree)
- **Mission prompt:** `workspace/cost-intel/mission-phase1.md`
- **This doc:** `workspace/cost-intel/PHASE1_COMPLETE.md`
