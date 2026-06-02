# Factory Mission Prompt — Cost Intelligence Phase 2

## Mission
Implement Phase 2 (Quality Correlation) of the Cost Intelligence project. Add the differentiator: cost-per-quality-point (CPQP) metric, waste detection, quality score import adapters, model comparison, and optimization suggestions.

## Context
- **Project repo**: https://github.com/onicarps/cost-intel
- **Workspace**: `workspace/cost-intel/` in the cost-intel Hermes profile
- **AGENTS.md**: Read the workspace AGENTS.md first — it has the full project spec, build rules, and file tree
- **Plan**: `workspace/cost-intel/plan.md` — Phase 2 section starts at line 851. Full TDD steps, SQL migrations, and inline code for all 6 tasks.
- **Phase 1 is COMPLETE**: All cost-only CLI commands work. 77 tests passing. `record`, `report`, `trends`, `export`, `budget`, `estimate`, `ingest-api-responses`, `refresh-pricing` all functional.
- **Linear issues**: ONI-54 through ONI-59 (Phase 2 milestone + 5 tasks)

## Database State
Phase 1 schema (migration 001) is already applied. Phase 2 adds:
- Migration 002: `quality_scores` table + `cost_run_cpqp` view with PERCENT_RANK() percentile ratings
- The `cost_run_cpqp` view computes CPQP = total_cost / max(combined_score, 0.01) with A/B/C/D/F ratings

## Phase 2 Tasks (in order)

### ONI-54: Task 2.0 — Schema Migration 002
**Precondition for all other Phase 2 tasks. Must run first.**

Create `src/cost_intel/migrations/002_add_quality.sql`:
- `quality_scores` table with: score_id (AUTOINCREMENT), run_id (FK to cost_runs), source, source_run_id, combined_score (CHECK 0.0-1.0), eval_dimensions (JSON), eval_weights (JSON), notes, imported_at
- Indexes: idx_quality_run, idx_quality_source, idx_quality_score
- `DROP VIEW IF EXISTS cost_run_cpqp` then `CREATE VIEW cost_run_cpqp` with PERCENT_RANK() window function for A/B/C/D/F ratings

The view formula:
```sql
CASE
    WHEN qs.combined_score IS NULL THEN 'N/A'
    WHEN PERCENT_RANK() OVER (
        ORDER BY SUM(crc.call_cost) / MAX(qs.combined_score, 0.01)
    ) <= 0.25 THEN 'A'
    WHEN PERCENT_RANK() OVER (...) <= 0.50 THEN 'B'
    WHEN PERCENT_RANK() OVER (...) <= 0.75 THEN 'C'
    WHEN PERCENT_RANK() OVER (...) <= 0.90 THEN 'D'
    ELSE 'F'
END AS rating
```

Verify: migration_runner.py already exists from Phase 1. The runner should pick up 002 automatically.

Test: `tests/test_migrations.py` — verify quality_scores table exists, cost_run_cpqp view exists, version is 2, idempotent.

### ONI-55: Task 2.1 — Quality Score Import + Adapters
Create `src/cost_intel/quality.py`:
- `import_score(run_id, score, source, source_run_id, eval_dimensions, eval_weights, notes)` — stores a quality score, computes combined_score from dimensions+weights if score is None
- `compute_combined_score(dimensions, weights)` — weighted sum helper, validates weights sum to 1.0
- `get_cpqp(run_id)` — query cost_run_cpqp view for a single run
- `get_all_cpqp(days)` — get all CPQP results with optional time filter
- `get_waste_runs(days)` — find runs rated D or F
- `import_scores_csv(file, source, mapping=None)` — CSV import with optional JSON column mapping

Create `src/cost_intel/adapters/eval_harness.py`:
- `import_from_db(db_path)` — read scores from Eval Harness SQLite DB, call import_score()

Create `src/cost_intel/adapters/braintrust.py`:
- `import_from_api(api_key, project_id)` — fetch scores from Braintrust REST API, call import_score()

CLI additions in `cli.py`:
- `cost-intel import-scores --source csv --file scores.csv --mapping '{"run_id":"id"}'`
- `cost-intel import-scores --source eval-harness --db-path ~/.eval-harness/eval.db`
- `cost-intel import-scores --source braintrust --api-key KEY`
- `cost-intel cpqp --last 30d --waste-only`

Test: `tests/test_quality.py` — import_score, compute_combined_score, CSV import, CPQP calculation, waste runs, division-by-zero guard (score=0 → CPQP=$100)

### ONI-56: Task 2.2 — CPQP Report + Waste CLI
Extend `cost-intel report` and add `cost-intel waste` command:
- `cost-intel cpqp --last 30d` — table with run_id, label, total_cost, combined_score, cpqp, rating
- `cost-intel cpqp --waste-only` — filter to D and F rated runs
- `cost-intel waste` — alias for cpqp --waste-only with waste index summary

Test: verify CPQP ordering (expensive low-quality > cheap high-quality), rating column present, waste-only filter works

### ONI-57: Task 2.3 — Model Comparison with Efficiency Delta
Create `src/cost_intel/compare.py`:
- `compare_models(label, models_filter)` — for each model: avg_cpqp, run_count, delta_cpqp relative to best (lowest CPQP)
- Warning when filter returns empty results

CLI: `cost-intel compare-models --label "summarization" --models "gpt-4o,claude-sonnet-4"`

Test: verify delta_cpqp calculation, empty filter warning

### ONI-58: Task 2.4 — Optimization with Bug Fixes
Create `src/cost_intel/optimize.py`:
- `suggest_model_routing(label, min_runs=1)` — suggest cheapest model for each task label
- `get_waste_index(days, target_cpqp=None)` — waste index = cost of D+F runs / total cost
- Use `rating IN ('D', 'F')` from cost_run_cpqp view (NOT hardcoded CPQP thresholds)
- `get_runs_above_target_cpqp(target_cpqp)` — find runs exceeding target

CLI: `cost-intel optimize --suggest-model-routing --target-cpqp 0.05`

**CRITICAL FIX**: The `--suggest-model-routing` bool parameter must NOT shadow the function import. Use `route: bool = typer.Option(False, "--suggest-model-routing", ...)` and call `suggest_model_routing()` inside the if block.

Test: model routing suggestions, waste index calculation, target CPQP query, no bool shadowing crash

### ONI-59: Task 2.5 — CPQP Trend Analysis
Create `src/cost_intel/trends.py`:
- `get_cpqp_trend(window_days=7)` — compare this week's avg CPQP vs last week's, return {this_window, prior_window, ratio}

Extend CLI: `cost-intel trends --metric cpqp --days 14`

Test: verify week-over-week ratio calculation, handles empty windows

## Rules (NON-NEGOTIABLE)
1. **TDD always** — write failing test FIRST, run to confirm failure, then implement, then verify tests pass
2. **Work task-by-task in order** (2.0 → 2.1 → 2.2 → 2.3 → 2.4 → 2.5)
3. **Commit after every task** — `git add -A && git commit -m "feat: Task 2.X — description"`
4. **Branch naming**: `cost-intel/ONI-XX-description` (e.g., `cost-intel/ONI-54-migration-002`)
5. **Do NOT skip ahead** — each task depends on the previous (especially 2.0 → everything else)
6. **Run full test suite before every commit** — `pytest tests/ -v --cov=src`
7. **ruff check + ruff format** before every commit
8. **`from typing import Optional`** in every new module using Optional
9. **After each task, run `cost-intel --help`** to verify all commands are registered

## Phase 2 Gate (must pass before Phase 3)
- `pip install -e .` works
- `pytest tests/ -v` passes (all Phase 1 + Phase 2 tests)
- Manual validation:
  ```bash
  cost-intel import-scores --source csv --file test.csv
  cost-intel cpqp --last 30d
  cost-intel waste
  cost-intel compare-models --label "summarization"
  cost-intel optimize --target-cpqp 0.05
  cost-intel trends --metric cpqp --days 14
  ```

## Important Implementation Notes

1. **PERCENT_RANK() in SQLite**: The CPQP view uses `PERCENT_RANK() OVER (ORDER BY cpqp_value)` window function. This requires SQLite 3.25+ (supports window functions). Verify with `sqlite3 --version`.

2. **config.yaml weights**: The `eval_weights` config section has format:
   ```yaml
   eval_weights:
     csv:
       faithfulness: 0.5
       task_completion: 0.5
     eval_harness:
       faithfulness: 0.3
       task_completion: 0.7
   ```

3. **Division by zero guard**: CPQP = total_cost / max(combined_score, 0.01). When score=0, CPQP=$100 which correctly flags as F-rated.

4. **No hardcoded dollar thresholds**: All efficiency ratings come from PERCENT_RANK() in the view, NOT from hardcoded CPQP thresholds in Python.

5. **combined_score computation**: When importing with multiple eval dimensions, combined_score = Σ(weight_i × score_i). Default weights: equal weighting. Configurable per source via config.yaml.
