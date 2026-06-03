# Cost Intelligence — Phase 2 Implementation Complete

> **Date:** June 3, 2026
> **Status:** Phase 2 (Quality Correlation) — ALL 6 tasks complete
> **Tests:** 123 passing (77 Phase 1 + 46 Phase 2), ruff clean
> **GitHub:** https://github.com/onicarps/cost-intel (6 new branches pushed)

---

## What Was Built

The quality-correlation layer on top of the Phase 1 cost foundation. The CLI
now correlates spend with eval scores, produces a **cost-per-quality-point
(CPQP)** metric with percentile-based A/B/C/D/F ratings, surfaces waste, and
suggests cheaper model routing.

### New Source Modules

| Module | Purpose |
|--------|---------|
| `src/cost_intel/migrations/002_add_quality.sql` | `quality_scores` table + `cost_run_cpqp` view (PERCENT_RANK ratings) |
| `src/cost_intel/quality.py` | `import_score`, `compute_combined_score`, CSV import (with `--mapping`), `get_cpqp`, `get_all_cpqp` (days filter), `get_waste_runs` |
| `src/cost_intel/adapters/eval_harness.py` | Eval Harness SQLite import (`results` / `eval_results` table fallback) |
| `src/cost_intel/adapters/braintrust.py` | Braintrust REST adapter (httpx Client, project + experiment fetch) |
| `src/cost_intel/compare.py` | `compare_models` with `avg_cpqp` + `delta_cpqp` baseline |
| `src/cost_intel/optimize.py` | `suggest_model_routing(min_runs)`, `get_waste_index(days, target_cpqp)`, `get_runs_above_target_cpqp` |
| `src/cost_intel/trends.py` | `get_cpqp_trend(window_days)` week-over-week ratio |

### CLI Commands (all working)

```
cost-intel cpqp [--last 7d] [--waste-only]              → percentile CPQP report
cost-intel waste [--last 7d]                            → D/F runs + waste-index summary
cost-intel compare-models [--label X] [--models a,b]    → cost + CPQP delta
cost-intel optimize [--target-cpqp 0.05]
                    [--suggest-model-routing]
                    [--min-runs N]                      → waste index | routing | target CPQP
cost-intel trends --metric cpqp [--days 14]             → week-over-week CPQP trend
cost-intel import-scores --source csv --file scores.csv
                         --mapping '{"run_id":"id"}'    → CSV import w/ optional remap
cost-intel import-scores --source eval-harness
                         --db-path ~/.eval-harness/db   → Eval Harness adapter
cost-intel import-scores --source braintrust
                         --api-key KEY
                         --project-id ID                → Braintrust adapter
```

---

## Branches Pushed

| Task   | Branch                                            | Linear  |
|--------|---------------------------------------------------|---------|
| 2.0    | `cost-intel/ONI-54-migration-002`                 | ONI-54  |
| 2.1    | `cost-intel/ONI-55-quality-import`                | ONI-55  |
| 2.2    | `cost-intel/ONI-56-cpqp-waste-cli`                | ONI-56  |
| 2.3    | `cost-intel/ONI-57-compare-models`                | ONI-57  |
| 2.4    | `cost-intel/ONI-58-optimize`                      | ONI-58  |
| 2.5    | `cost-intel/ONI-59-cpqp-trends`                   | ONI-59  |

Each branch builds linearly on the previous; merge in numeric order.

---

## Test Coverage (123 tests, +46 from Phase 1)

| Test File              | New Tests | What's Covered |
|------------------------|-----------|----------------|
| `test_migrations.py`   | 6         | Migration 002 quality_scores table, cost_run_cpqp view, idempotency, CHECK constraint, rating column |
| `test_quality.py`      | 13        | import_score, clamping, division-by-zero guard, combined_score weighting, CSV import (with mapping), waste runs, days filter |
| `test_adapters.py`     | 3         | Eval Harness DB read, missing-table fallback, Braintrust httpx Client mock |
| `test_cli_cpqp.py`     | 5         | Rating column, --waste-only filter, --last parser, empty DB |
| `test_compare.py`      | 5         | basic comparison, CPQP delta baseline, empty filter, --models filter, CLI empty warning |
| `test_optimize.py`     | 9         | routing suggestions, min_runs filter, waste_index SQL, target_cpqp variant, runs_above_target, no-shadow CLI crash |
| `test_trends.py`       | 5         | cpqp trend keys, empty DB, CLI metric/cpqp, CLI legacy spending |

---

## Phase 2 Gate — Validation Output

All gate commands executed successfully against a freshly seeded DB:

```text
$ cost-intel import-scores --source csv --file scores.csv
✓ Imported 1 scores from scores.csv

$ cost-intel cpqp --last 30d
Cost-Per-Quality-Point (CPQP) — last 30d
3× expensive low-quality runs rated D ($75 CPQP)
8× cheap high-quality runs rated A ($0.05 CPQP)
ordering matches intuition (D > C > A)

$ cost-intel waste
Waste Index: 96.0% ($45.00 of $46.86)
Lists the 3 D-rated runs

$ cost-intel compare-models --label summarization
gpt-4o-mini  Δ +0.0000 (baseline, cheapest)
gpt-4o       Δ +74.9500

$ cost-intel optimize --target-cpqp 0.05
4 run(s) exceed target CPQP

$ cost-intel trends --metric cpqp --days 14
This window $18.9756 | Prior $0.0000 | Ratio 0.00
```

---

## Audit Fixes Applied (from `mission-phase2.md` / `plan.md`)

| Finding                                                  | Severity  | Resolution                                                                                          |
|----------------------------------------------------------|-----------|-----------------------------------------------------------------------------------------------------|
| `migration_runner.get_current_version()` opened `:memory:` | HIGH      | Switched to `cost_intel.db.get_connection()` so the real DB version is read (Phase 1 latent bug).   |
| CPQP percentile ratings missing                          | CRITICAL  | Migration 002 view uses `PERCENT_RANK() OVER (ORDER BY ...)` for A/B/C/D/F.                          |
| Division-by-zero on score=0                              | CRITICAL  | View uses `MAX(qs.combined_score, 0.01)` as denominator floor.                                       |
| `get_waste_index()` had aggregates in WHERE              | CRITICAL  | Rewritten using `cost_run_cpqp` view with `rating IN ('D','F')` (or `cpqp > ?` when target given).  |
| `optimize` CLI bool flag shadowed function               | CRITICAL  | Parameter renamed to `route: bool`; function imported as `suggest_model_routing`.                    |
| Eval Harness adapter stubbed                             | HIGH      | Full implementation with `results` → `eval_results` table fallback.                                  |
| Braintrust adapter stubbed                               | HIGH      | Full implementation using `httpx.Client` (mock-friendly).                                            |
| CSV `--mapping` missing                                  | HIGH      | `import_scores_csv(mapping={"run_id":"id","score":"quality"})` supported.                            |
| `combined_score` not computed from dimensions            | HIGH      | `compute_combined_score()` with auto-normalised weights.                                            |
| `--target-cpqp` had no behavior                          | HIGH      | `get_runs_above_target_cpqp()` + CLI table.                                                         |
| `--last`/`--days` missing on `cpqp`                      | HIGH      | `cpqp` & `waste` both accept `--last 7d` via canonical `parse_window`.                              |
| No CPQP trend                                            | MEDIUM    | `get_cpqp_trend()` + `trends --metric cpqp`.                                                        |
| No Model Efficiency Delta                                | MEDIUM    | `compare_models` returns `delta_cpqp` relative to lowest-CPQP model.                                |

---

## Known Issues / Considerations

1. **Single-quality-score-per-run** — the schema allows multiple `quality_scores`
   rows per `run_id`. The current CPQP view joins by `qs.combined_score` from a
   single row; if multiple scores exist for the same run, the aggregation is
   undefined. A follow-up could `GROUP BY run_id` on the score join or pick the
   most recent score. Out of scope for Phase 2.

2. **Braintrust pagination** — the adapter fetches a single page of events per
   experiment. Real Braintrust experiments often have hundreds of events. Add
   `?limit=…&cursor=…` pagination in Phase 3 if real-world testing demands it.

3. **`cpqp` with no quality data** — emits a friendly "no results" message.
   The behavior of `optimize --target-cpqp` with no quality data is to print an
   empty table.

4. **PERCENT_RANK on small datasets** — with only 1–2 scored runs the rating
   column is always `A` (rank=0). The tests use ≥10 runs to verify partitioning.

---

## What's Next: Phase 3 (CI/CD + Alerts)

**Approach:** Individual droid exec calls (small tasks).
**Tasks:**
- Task 3.1 — `gate.py` cost gate (`cost-intel gate --max-avg-cpqp 0.10 --window 7d`)
- Task 3.2 — GitHub Actions example YAML
- Task 3.3 — Slack webhook + SMTP email alerts (`alerts.py`)

The Phase 2 modules are the foundation for Phase 3: `gate.py` will reuse
`get_cpqp_trend`, `get_waste_index`, and `get_runs_above_target_cpqp`.

---

## How to Continue in a New Session

```bash
cd ~/.hermes/profiles/cost-intel/workspace/cost-intel
source .venv/bin/activate
pytest tests/ -q      # → 123 passed

# All Phase 2 branches are on origin. To merge into main:
git checkout main
for br in cost-intel/ONI-54-migration-002 \
          cost-intel/ONI-55-quality-import \
          cost-intel/ONI-56-cpqp-waste-cli \
          cost-intel/ONI-57-compare-models \
          cost-intel/ONI-58-optimize \
          cost-intel/ONI-59-cpqp-trends; do
    git merge --no-ff "$br"
done
git push origin main
```
