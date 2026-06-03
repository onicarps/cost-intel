# SESSION HANDOFF — Cost Intelligence

> **Last session:** June 3, 2026
> **Current state:** Phase 1 COMPLETE, Phase 2 ready to start
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
   pytest tests/ -q              # → 77 passed
   ```

3. **Update Linear issues** (CLI wasn't available last session):
   - Mark ONI-43 (Phase 1 milestone) as **Done**
   - Mark ONI-44 through ONI-53 (Phase 1 tasks) as **Done**
   - Mark ONI-62 (duration parser) as **Done**

4. **Update Notion page** (ntn CLI requires browser auth — may need user present):
   - Page: https://notion.so/Cost-Intelligence-373e2527f3178147957ad4e1705278db
   - Mark Phase 1 as complete
   - Note: Phase 2 ready to start

5. **Kick off Phase 2** via Factory Droid:
   ```bash
   # Extract FACTORY_API_KEY from .env
   FACTORY_API_KEY=$(grep '^FACTORY_API_KEY' ~/.hermes/profiles/cost-intel/.env | cut -d= -f2-)
   cd ~/.hermes/profiles/cost-intel/workspace/cost-intel
   env FACTORY_API_KEY="$FACTORY_API_KEY" droid exec --auto high -f mission-phase2.md
   ```

---

## Project Summary

**What:** `cost-intel` — standalone Python CLI that tracks AI spending at the task level, optionally correlates with quality scores, produces cost-efficiency metrics.

**Value prop:** "No unified cost-quality metric in a CLI-native package."

**Repo:** https://github.com/onicarps/cost-intel (main branch, 9 commits)

---

## What Exists (Phase 1 — Complete)

### Source Modules (16 files, ~1350 LOC)

| Module | Purpose | LOC |
|--------|---------|-----|
| `__init__.py` | `__version__ = "0.1.0"` | 3 |
| `__main__.py` | `python -m cost_intel` entry | 6 |
| `cli.py` | Typer app, all CLI commands, sub-apps (budget, pricing) | 360 |
| `config.py` | YAML config loader with caching | 47 |
| `db.py` | Connection manager, `connect()` contextmanager, `init_db()` | 65 |
| `migration_runner.py` | Numbered SQL migration runner | 99 |
| `duration.py` | `parse_window("7d")` → 7 (CANONICAL) | 43 |
| `pricing.py` | OpenRouter fetch, historical upsert, refresh CLI | 221 |
| `record.py` | `record_run()`, `get_run()`, `get_run_calls()` | 163 |
| `report.py` | Summary, by-model, by-label, by-day with time-window | 137 |
| `budget.py` | `set_budget()`, `get_budget_status()` | 74 |
| `estimate.py` | `estimate_tokens()`, `estimate_cost()` (tiktoken) | 58 |
| `ingest.py` | `ingest_jsonl()` with provider token extraction | 99 |
| `utils.py` | `now_iso()`, `retry()` | 40 |
| `migrations/001_initial.sql` | Phase 1 schema (5 tables + indexes) | ~60 |

### CLI Commands (all working)

```
cost-intel --version                          → 0.1.0
cost-intel record --model M -i 100 -o 50      → record a run
cost-intel report --last 7d --by-model        → cost report
cost-intel trends --last 30d                  → daily trends
cost-intel export --format csv --last 7d      → CSV export
cost-intel budget set --monthly 500           → set budget
cost-intel budget status                      → show status
cost-intel refresh-pricing                    → fetch pricing
cost-intel pricing set/show --model M         → manual pricing
cost-intel estimate "text" --model gpt-4      → token estimation
cost-intel ingest-api-responses file.jsonl    → ingest JSONL
```

### Tests (77 passing, 0 lint errors)

| File | Tests | Coverage |
|------|-------|----------|
| test_config.py | 5 | Config loader, caching, eval weights |
| test_db.py | 12 | Schema, migrations, WAL, busy_timeout, contextmanager |
| test_duration.py | 12 | parse_window (d/h/w/bare/invalid) |
| test_estimate.py | 5 | Token estimation, cost prediction |
| test_ingest.py | 9 | Token extraction, JSONL ingest, error handling |
| test_pricing.py | 10 | Upsert, historical, manual, refresh |
| test_record.py | 11 | Recording, cost computation, getters |
| test_report.py | 9 | Summary, by-model/label/day, budget |
| test_utils.py | 3 | now_iso, retry |

### CI/CD
- `.github/workflows/ci.yml` — ruff + pytest on Python 3.11/3.12
- `scripts/bootstrap.sh` — one-command dev setup
- `scripts/dogfood.sh` — ingest Hermes logs + show report

---

## Key Bugs Found During Phase 1 (already fixed)

1. **OpenRouter pricing math:** API returns per-million-token prices → multiply by `1_000_000` (not `1_000`). Fixed in `refresh_all_pricing()`.

2. **Same-day upsert PK conflict:** Composite PK `(model_id, effective_date)` caused UNIQUE violations on same-day re-upsert. Fixed: same-day → UPDATE in place, different-day → mark old `is_current=0` + INSERT new row.

3. **SQLite datetime format:** ISO 8601 timestamps with timezone offsets (`2025-01-01T00:00:00+00:00`) don't compare correctly with SQLite's `datetime('now', '-N days')`. Use `YYYY-MM-DD HH:MM:SS` format for manual inserts.

4. **Dict vs list params:** `conn.execute(sql, dict)` with `?` placeholders fails. Use lists: `conn.execute(sql, [value])`.

---

## What's Next: Phase 2 (Quality Correlation)

### Mission Prompt
**File:** `mission-phase2.md` (in workspace root)
**Approach:** Factory Droid Mission (6 tasks, good parallelism after 2.0+2.1)
**Estimated:** ~31 new tests, 6 new modules/files

### Tasks (in order)

| Task | Linear | Description | Key Files |
|------|--------|-------------|-----------|
| 2.0 | ONI-54 | Migration 002: quality_scores table + CPQP view with PERCENT_RANK() | `002_add_quality.sql` |
| 2.1 | ONI-55 | Quality import + adapters (csv, eval_harness, braintrust) | `quality.py`, `adapters/` |
| 2.2 | ONI-56 | CPQP report + waste CLI | `cli.py` |
| 2.3 | ONI-57 | Model comparison with efficiency delta | `compare.py` |
| 2.4 | ONI-58 | Optimization (waste index, target CPQP, bug fixes) | `optimize.py` |
| 2.5 | ONI-59 | CPQP trend analysis (week-over-week) | extend `report.py` |

### Phase 2 Gate
```bash
pytest tests/ -v                    # All Phase 1 + Phase 2 tests pass
cost-intel import-scores --source csv --file test.csv
cost-intel cpqp --last 30d
cost-intel waste
cost-intel compare-models --label "summarization"
cost-intel optimize --target-cpqp 0.05
cost-intel trends --metric cpqp --days 14
```

---

## Phase 3 (CI/CD + Alerts) — After Phase 2

**Approach:** Individual droid exec calls (too small for Missions)
**Tasks:**
- Task 3.0: Duration parser (already done in Phase 1)
- Task 3.1: Cost gate (`gate.py`) — `cost-intel gate --max-avg-cpqp 0.10 --window 7d`
- Task 3.2: GitHub Actions example YAML
- Task 3.3: Budget alerts (`alerts.py`) — Slack webhook + SMTP email

---

## Phase 4 (Multi-Agent) — After Phase 3

**Approach:** Two split Missions
- **Mission A (OTel track):** Tasks 4.0+4.1+4.2 — migration 003, span ingestion, trace cost breakdown
- **Mission B (Optimization track):** Tasks 4.3+4.4 — prompt optimization, budget enforcement

---

## Environment & Credentials

**Profile:** `~/.hermes/profiles/cost-intel/`
**Venv:** `~/.hermes/profiles/cost-intel/workspace/cost-intel/.venv/`
**Workspace:** `~/.hermes/profiles/cost-intel/workspace/cost-intel/`

**API keys in `~/.hermes/profiles/cost-intel/.env`:**
- `OPENROUTER_API_KEY`
- `LINEAR_API_KEY`
- `GITHUB_TOKEN`
- `FACTORY_API_KEY`
- `NOTION_API_TOKEN`

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
6. **Percentile-based ratings** — never hardcode dollar thresholds for efficiency ratings
7. **Standalone** — zero foreign keys to any other product
8. **Views use DROP+CREATE** — never `CREATE VIEW IF NOT EXISTS` in migrations

---

## Subagent Audit Results

A subagent (different model) reviewed the Factory Missions recommendation:

- **Phase 2:** Good fit for Missions (6 tasks, ~31 tests, parallelism after 2.0+2.1) ✅
- **Phase 3:** Individual droid exec (too small, only 3 real tasks) ✅
- **Phase 4:** Two split Missions (OTel track + optimization track) ✅

Key risks flagged:
- Migration 002 errors compound downstream — verify Phase 2 Gate carefully
- Multiple Phase 2 tasks modify `cli.py` — work sequentially to avoid merge conflicts
- PERCENT_RANK() requires SQLite 3.25+ — verify `sqlite3 --version`
- bool parameter shadowing in `optimize --suggest-model-routing` — already fixed in plan

---

## File Locations Reference

| File | Purpose |
|------|---------|
| `SOUL.md` (profile root) | Mission + protocols |
| `AGENTS.md` (workspace) | Build rules + conventions |
| `PHASE1_COMPLETE.md` (workspace) | Phase 1 handoff details |
| `mission-phase2.md` (workspace) | Factory Droid Phase 2 prompt |
| `plan.md` (workspace) | Full 4-phase plan (4297 lines) |
| `research/cost-intelligence/plan.md` (profile) | Original audited plan |
| `skills/devops/factory-ai/SKILL.md` (profile) | Factory.ai orchestration guide |
| `.github/workflows/ci.yml` (workspace) | CI pipeline |
| `scripts/bootstrap.sh` (workspace) | Dev setup |
| `scripts/dogfood.sh` (workspace) | Dogfood script |
