# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-03

### Added

**Phase 1 — Cost-Only Foundation**
- Project scaffold with hatchling build backend, src-layout, Typer + Rich CLI
- YAML config loader with caching (`~/.cost-intel/config.yaml`)
- SQLite database (WAL mode, busy_timeout=5000) with numbered migration runner
- Model pricing with historical tracking — composite PK `(model_id, effective_date)`, same-day UPDATE vs cross-date INSERT
- Cost run recording with cache tokens, raw_response truncation, labels, latency
- Aggregate reports: summary, by-model, by-label, by-day with time-window filtering (`7d`, `30d`, `2w`)
- CSV/JSON export
- Budget management (set monthly budget, check status with spending)
- Token/cost estimation via tiktoken pre-call estimation
- JSONL ingestion with provider-specific cache token extraction (OpenRouter/Anthropic/OpenAI)
- OpenRouter pricing refresh (`cost-intel refresh-pricing`) + manual override (`cost-intel pricing set`)
- CI pipeline (ruff lint + format check, pytest on Python 3.11/3.12)
- Bootstrap script (`scripts/bootstrap.sh`) and dogfood script (`scripts/dogfood.sh`)
- 77 tests

**Phase 2 — Quality Correlation**
- Migration 002: `quality_scores` table + `cost_run_cpqp` view with `PERCENT_RANK()` percentile ratings (A/B/C/D/F)
- CPQP (cost-per-quality-point) report with `--last` window filter
- Waste analysis — identify runs with D or F efficiency ratings, compute waste index
- Model comparison with CPQP delta (`cost-intel compare-models`)
- Optimization suggestions: model routing, target CPQP, waste index
- Week-over-week CPQP trend (`cost-intel trends --metric cpqp`)
- Quality score import adapters: Eval Harness (SQLite), Braintrust (REST API), CSV
- CSV import command (`cost-intel import`) with format auto-detection
- 46 additional tests (123 total)

**Phase 3 — CI/CD + Alerts**
- CI/CD cost gate (`cost-intel gate`): CPQP threshold, waste-index threshold, budget-check; exits 0/1; JSON output
- Budget alerts: Slack webhook + SMTP email dispatch
- GitHub Actions example workflow
- 22 additional tests (145 total)

**Phase 4 — Multi-Agent + Advanced**
- Migration 003: `trace_id`, `span_id`, `parent_span_id` columns on `cost_runs` + indexes
- OpenTelemetry span ingestion (`cost-intel trace-cost`) with span-tree roll-up + CPQP at each span level
- Prompt optimization analysis (`cost-intel prompt-opt`): high-cost pattern detection + trimming suggestions
- Budget enforcement guard (`cost-intel guard`): hard-stop with threshold, exits non-zero when exceeded
- 19 additional tests (164 total)

**Packaging + Distribution**
- PyPI publication (trusted publishing via GitHub Actions on tag)
- Full PyPI metadata: classifiers, keywords, project.urls
- README with install instructions, feature overview, command reference, config example
- GitHub Actions publish workflow (build + upload on `v*` tags)
- Auto generated CHANGELOG

[0.1.0]: https://github.com/onicarps/cost-intel/releases/tag/v0.1.0
