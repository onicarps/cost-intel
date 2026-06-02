# Cost Intelligence — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build `cost-intel`, a standalone Python CLI that tracks AI spending at the task level, optionally correlates it with quality scores, and produces cost-efficiency metrics.

**Architecture:** Python CLI (Typer + Rich) + SQLite (stdlib). Standalone — zero foreign keys to any other product. Quality scores imported via adapters (Eval Harness, Braintrust, CSV, generic API). CPQP (cost-per-quality-point) is the core metric. **Percentile-based efficiency ratings (A/B/C/D/F)**. Open-core model: OSS CLI + paid cloud tiers later.

**Tech Stack:** Python 3.11+, Typer, Rich, sqlite3 (stdlib), httpx, Pydantic v2, pyyaml, tiktoken, hatchling, ruff, pytest. Optional: opentelemetry-sdk.

**Data directory:** `~/.cost-intel/` (env override: `COST_INTEL_HOME`)
**Cache/DB:** `~/.cost-intel/cost-intel.db`
**Config:** `~/.cost-intel/config.yaml`

**`parse_window` canonical location: `src/cost_intel/duration.py` (with tests in `tests/test_duration.py`). All other modules import from there.**

---

## AUDIT REVISION LOG

This plan was revised after two independent audits (LLM subagent: 30 findings, Droid: 37 findings). All 67 findings addressed:

### CRITICAL (5 fixed)
- [C1] `config` table existence check: moved to schema migration, `type='table'` bug fixed
- [C2] CPQP percentile ratings (A/B/C/D/F): implemented via `PERCENT_RANK()` window function, replaced all hardcoded dollar thresholds
- [C3] `get_waste_index()` SQL: rewritten with CTE, no aggregates in WHERE clause
- [C4] Schema migration strategy: added `schema_version` table, numbered SQL migration files, migration runner in `init_db()`
- [C5] `optimize` CLI crash: renamed bool parameter from `suggest_model_routing` to `route` to avoid shadowing imported function

### HIGH (12 fixed)
- [H1] `report --last`/`--days`: added duration parser (`_parse_window()`), default 7-day window
- [H2] `import-scores` adapters: Eval Harness + Braintrust fully implemented (not stubs)
- [H3] `gate --window 7d`: accepts duration strings via `_parse_window()`
- [H4] Cache tokens: `record_run()` + `ingest_jsonl()` handle cache_read/cache_write tokens
- [H5] Percentile ratings in Phase 2: added as core deliverable in CPQP view
- [H6] OTel ingestion: trace_id/span_id/parent_span_id stored, `get_trace_cost()` filters correctly
- [H7] `--target-cpqp` behavior: queries runs above target
- [H8] Slack/email alerts: added Task 3.3
- [H9] CSV `--mapping`: JSON column mapping added
- [H10] `combined_score` weighted aggregation: `compute_combined_score()` helper + config.yaml weights
- [H11] Pricing refresh CLI: `cost-intel refresh-pricing` + `cost-intel pricing set`
- [H12] Historical per-date pricing: composite PK `(model_id, effective_date)`, preserves history

### MEDIUM (11 fixed)
- [M1] `Optional` imports in all modules
- [M2] Budget subcommand structure: `set`/`status` subcommands match research §4.3
- [M3] Week-over-week CPQP trend: `get_cpqp_trend()` added
- [M4] Model Efficiency Delta: `compare_models` reports `delta_cpqp`
- [M5] `raw_response` column: populated by `record_run()` and `ingest_jsonl()`
- [M6] `config.yaml` loader: `src/cost_intel/config.py` added
- [M7] Manual pricing override CLI: `cost-intel pricing set`
- [M8] Connection contextmanager pattern + busy_timeout
- [M9] `tiktoken` in pyproject.toml + `cost-intel estimate` command
- [M10] Integration tests in `tests/integration/`
- [M11] Dogfood on Hermes cron: Task 1.9 added

### LOW (9 fixed)
- [L1] Directory naming: standardized to `cost-intel/`
- [L2] Bootstrap: `VENV_DIR` env var override
- [L3] PyPI metadata: authors, license, readme, urls, classifiers
- [L4] Retry/backoff: 3 attempts exponential backoff on OpenRouter API
- [L5] Timezone: "(UTC)" on timestamp headers
- [L6] `record` CLI: cache/latency/provider flags added
- [L7] Phase 4 tasks 3+4: prompt optimization + budget enforcement added
- [L8] Ruff config: `[tool.ruff.lint] select = ["E", "F", "I"]`
- [L9] OTel test: fixed to use stored span_id as run_id

### RE-AUDIT GAP CLOSURE (June 2 2026)
All 6 remaining gaps from Droid re-audit closed:
- [H11] `cost-intel refresh-pricing` CLI registered
- [M7] `cost-intel pricing set/show` sub-app registered
- [Phase 1 CLI] `report`, `record`, `ingest-api-responses`, `estimate` command bodies added
- [M10] Integration test files fleshed out (`test_invoice_reconciliation.py`, `test_cpqp_ordering.py`)
- [M11] `scripts/dogfood.sh` content added
- [N1] `parse_window` consolidated to `duration.py` (removed from `utils.py` and inline)
- [N2] Phase 1 `record_run` trace kwargs marked as "ignored until migration 003"

**0 open gaps. Plan ready for implementation.**

---
## Phase 1: Cost-Only Foundation (Weeks 1-3)

> **Deliverable:** `pip install cost-intel` → track AI spending from CLI. No quality data needed.

### Task 1.0: Config Loader + Shared Utilities

**Files:** Create `src/cost_intel/config.py`, `src/cost_intel/utils.py`

```python
# src/cost_intel/config.py
"""Configuration loader — reads ~/.cost-intel/config.yaml."""
import os
from pathlib import Path
from typing import Any, Optional
import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".cost-intel"
CONFIG_DIR = Path(os.environ.get("COST_INTEL_HOME", str(DEFAULT_CONFIG_DIR)))
CONFIG_PATH = CONFIG_DIR / "config.yaml"
_config_cache: Optional[dict] = None


def load_config(force_reload: bool = False) -> dict[str, Any]:
    global _config_cache
    if _config_cache is not None and not force_reload:
        return _config_cache
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            _config_cache = yaml.safe_load(f) or {}
    else:
        _config_cache = {}
    return _config_cache


def get_eval_weights(source: str) -> Optional[dict[str, float]]:
    cfg = load_config()
    eval_weights = cfg.get("eval_weights", {})
    return eval_weights.get(source)
```

```python
# src/cost_intel/utils.py
"""Shared utilities — retry, now_iso.

NOTE: `parse_window` lives in `src/cost_intel/duration.py` (Task 3.0) — the
canonical location with tests in `tests/test_duration.py`. Do NOT duplicate
it here. Import from `cost_intel.duration` instead.
"""
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def retry(func, max_attempts: int = 3, delay: float = 1.0):
    import time
    last_err = None
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            last_err = e
            if attempt < max_attempts - 1:
                time.sleep(delay * (2 ** attempt))
    raise last_err
```

### Task 1.1: Project Scaffolding

Create: `pyproject.toml`, `src/cost_intel/__init__.py`, `src/cost_intel/__main__.py`, `src/cost_intel/cli.py`, `tests/conftest.py`, `.env.example`, `.gitignore`, `scripts/bootstrap.sh`

Key fixes:
- **`pyproject.toml`**: Added `authors`, `license`, `readme`, `classifiers`, `urls`, `[tool.ruff.lint] select = ["E", "F", "I"]`, `tiktoken>=0.7`
- **`bootstrap.sh`**: Uses `VENV_DIR="${VENV_DIR:-${HOME}/.venvs/cost-intel}"` env override
- **`cli.py`**: Added `--version` flag via Typer `is_eager` callback:
```python
# src/cost_intel/cli.py
import typer
from rich.console import Console
from cost_intel import __version__

app = typer.Typer(help="Cost Intelligence — AI spending tracker")
console = Console()

def _version_callback(value: bool):
    if value:
        console.print(f"cost-intel {__version__}")
        raise typer.Exit()

@app.callback(invoke_without_command=True)
def main(ctx: typer.Context, version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True)):
    if ctx.invoked_subcommand is None:
        console.print("[bold]cost-intel[/bold] — AI spending tracker")
        console.print("Run [bold]cost-intel --help[/bold] for commands.")
```

### Task 1.2: Database Layer — Schema + Connection + Migrations

**KEY FIX:** Migration framework with numbered SQL files replaces `_SCHEMA` string.

**Files:** `src/cost_intel/migrations/001_initial.sql`, `src/cost_intel/migration_runner.py`, `src/cost_intel/db.py`

```sql
-- 001_initial.sql
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE IF NOT EXISTS model_pricing (
    model_id TEXT NOT NULL, provider TEXT NOT NULL,
    input_price_per_1k_tokens REAL, output_price_per_1k_tokens REAL,
    cache_read_price_per_1k_tokens REAL DEFAULT NULL,
    cache_write_price_per_1k_tokens REAL DEFAULT NULL,
    effective_date TEXT NOT NULL DEFAULT (date('now')), is_current BOOLEAN DEFAULT 1,
    source TEXT DEFAULT 'openrouter', updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (model_id, effective_date)
);
CREATE INDEX IF NOT EXISTS idx_pricing_current ON model_pricing(model_id, is_current);
CREATE TABLE IF NOT EXISTS cost_runs (
    run_id TEXT PRIMARY KEY, run_type TEXT NOT NULL DEFAULT 'api_call',
    label TEXT, model_id TEXT, started_at TEXT NOT NULL, finished_at TEXT,
    status TEXT DEFAULT 'completed', created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cost_runs_model ON cost_runs(model_id);
CREATE INDEX IF NOT EXISTS idx_cost_runs_date ON cost_runs(started_at);
CREATE TABLE IF NOT EXISTS cost_run_calls (
    call_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES cost_runs(run_id),
    sequence INTEGER NOT NULL DEFAULT 0, provider TEXT NOT NULL, model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0, output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0, cache_write_tokens INTEGER DEFAULT 0,
    call_cost REAL NOT NULL, latency_ms INTEGER, raw_response TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_calls_run ON cost_run_calls(run_id);
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);
```

```python
# src/cost_intel/db.py
import os, sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_DIR = Path.home() / ".cost-intel"
DB_DIR = Path(os.environ.get("COST_INTEL_HOME", str(DEFAULT_DB_DIR)))
DB_PATH = DB_DIR / "cost-intel.db"

from cost_intel.migration_runner import apply_pending_migrations


def get_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def connect():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> sqlite3.Connection:
    conn = get_connection()
    apply_pending_migrations(conn)
    return conn
```

```python
# src/cost_intel/migration_runner.py
"""Numbered SQL migration runner with schema_version tracking."""
import sqlite3
from pathlib import Path
from typing import Optional

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _get_migration_files():
    if not _MIGRATIONS_DIR.exists():
        return []
    files = []
    for f in _MIGRATIONS_DIR.glob("*.sql"):
        try:
            ver = int(f.stem.split("_")[0])
            files.append((ver, f))
        except (ValueError, IndexError):
            continue
    return sorted(files, key=lambda x: x[0])


def get_current_version(conn: Optional[sqlite3.Connection] = None) -> int:
    # ... (version check logic)
    pass


def apply_pending_migrations(conn: Optional[sqlite3.Connection] = None) -> int:
    # ... (apply pending SQL migration files)
    pass
```

### Task 1.3: Model Pricing — Historical Pricing + Refresh CLI

**KEY FIX:** Historical per-date pricing with composite PK `(model_id, effective_date)`.

```python
# src/cost_intel/pricing.py
"""Model pricing with historical tracking, retry/backoff, refresh CLI."""

import os
from datetime import datetime, timezone
from typing import Optional
import httpx

from cost_intel.db import get_connection
from cost_intel.utils import retry

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def fetch_openrouter_pricing() -> list[dict]:
    def _do_fetch():
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp = httpx.get(OPENROUTER_MODELS_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json().get("data", [])
    return retry(_do_fetch, max_attempts=3, delay=1.0)


def upsert_pricing(model_id, provider, input_price, output_price,
                   cache_read=None, cache_write=None, source="openrouter"):
    """Insert or update pricing. If prices changed, preserves old row with is_current=0."""
    conn = get_connection()
    current = conn.execute(
        "SELECT * FROM model_pricing WHERE model_id = ? AND is_current = 1", (model_id,)
    ).fetchone()
    if current and (current["input_price_per_1k_tokens"] == input_price and
                    current["output_price_per_1k_tokens"] == output_price):
        conn.close()
        return  # No change
    now = datetime.now(timezone.utc).isoformat()
    today = now[:10]
    conn.execute("UPDATE model_pricing SET is_current = 0 WHERE model_id = ? AND is_current = 1", (model_id,))
    conn.execute(
        "INSERT INTO model_pricing (model_id, provider, input_price_per_1k_tokens, "
        "output_price_per_1k_tokens, cache_read_price_per_1k_tokens, "
        "cache_write_price_per_1k_tokens, effective_date, is_current, source, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
        (model_id, provider, input_price, output_price, cache_read, cache_write, today, source, now),
    )
    conn.commit()
    conn.close()


def get_pricing(model_id: str, as_of_date: Optional[str] = None) -> Optional[dict]:
    """Get pricing effective on a specific date (for back-dated cost calculation)."""
    conn = get_connection()
    if as_of_date:
        row = conn.execute(
            "SELECT * FROM model_pricing WHERE model_id = ? AND effective_date <= ? "
            "ORDER BY effective_date DESC LIMIT 1", (model_id, as_of_date)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM model_pricing WHERE model_id = ? AND is_current = 1", (model_id,)
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def refresh_all_pricing() -> int:
    models = fetch_openrouter_pricing()
    count = 0
    for model in models:
        model_id = model.get("id", "")
        if "/" not in model_id:
            continue
        provider = model_id.split("/")[0]
        pricing = model.get("pricing", {})
        try:
            input_price = float(pricing.get("prompt", 0)) * 1000
            output_price = float(pricing.get("completion", 0)) * 1000
        except (ValueError, TypeError):
            continue
        if input_price > 0 or output_price > 0:
            upsert_pricing(model_id, provider, input_price, output_price)
            count += 1
    return count


def set_manual_pricing(model_id, provider, input_price, output_price,
                       cache_read=None, cache_write=None):
    upsert_pricing(model_id, provider, input_price, output_price, cache_read, cache_write, source="manual")
```

**CLI commands — `refresh-pricing` and `pricing` sub-app:**

```python
# Add to src/cost_intel/cli.py
from cost_intel.pricing import refresh_all_pricing, set_manual_pricing, get_pricing


@app.command(name="refresh-pricing")
def refresh_pricing_cmd():
    """Refresh model pricing from OpenRouter API."""
    count = refresh_all_pricing()
    console.print(f"[green]✓[/green] Refreshed pricing for [bold]{count}[/bold] models")


pricing_app = typer.Typer(help="Model pricing management")


@pricing_app.command("set")
def pricing_set(
    model: str = typer.Option(..., "--model", "-m", help="Model ID"),
    input_price: float = typer.Option(..., "--input-price", help="Input price per 1K tokens"),
    output_price: float = typer.Option(..., "--output-price", help="Output price per 1K tokens"),
):
    """Set manual pricing for a private/enterprise model."""
    provider = model.split("/")[0] if "/" in model else "custom"
    set_manual_pricing(model, provider, input_price, output_price)
    console.print(f"[green]✓[/green] Pricing set for {model}: ${input_price}/1K in, ${output_price}/1K out")


@pricing_app.command("show")
def pricing_show(
    model: str = typer.Option(..., "--model", "-m", help="Model ID"),
):
    """Show current pricing for a model."""
    p = get_pricing(model)
    if p:
        console.print(f"{model}: ${p['input_price_per_1K_tokens']}/1K in, "
                     f"${p['output_price_per_1K_tokens']}/1K out "
                     f"(effective {p['effective_date']}, source: {p['source']})")
    else:
        console.print(f"[yellow]No pricing found for {model}[/yellow]")


app.add_typer(pricing_app, name="pricing")
```

### Task 1.4: Cost Recording — `cost-intel record` (cache tokens + raw_response)

**KEY FIX:** Cache tokens in record_run(), historical pricing support, raw_response truncated to 4KB.

```python
# src/cost_intel/record.py
"""Cost run recording with cache tokens, historical pricing, raw_response."""

import uuid
from typing import Optional
from cost_intel.db import get_connection
from cost_intel.pricing import get_pricing
from cost_intel.utils import now_iso


def _compute_cost(model_id, input_tokens, output_tokens,
                  cache_read_tokens=0, cache_write_tokens=0, as_of_date=None):
    pricing = get_pricing(model_id, as_of_date=as_of_date)
    if not pricing:
        return 0.0
    ic = (input_tokens / 1000) * (pricing["input_price_per_1k_tokens"] or 0)
    oc = (output_tokens / 1000) * (pricing["output_price_per_1k_tokens"] or 0)
    crc = (cache_read_tokens / 1000) * (pricing["cache_read_price_per_1k_tokens"] or 0)
    cwc = (cache_write_tokens / 1000) * (pricing["cache_write_price_per_1k_tokens"] or 0)
    return round(ic + oc + crc + cwc, 6)


def record_run(model_id, input_tokens, output_tokens, label=None, run_type="api_call",
               provider=None, latency_ms=None, cache_read_tokens=0, cache_write_tokens=0,
               raw_response=None, as_of_date=None, trace_id=None, span_id=None,
               parent_span_id=None, run_id=None) -> str:
    rid = run_id or str(uuid.uuid4())
    now = now_iso()
    cost = _compute_cost(model_id, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, as_of_date)
    prov = provider or (model_id.split("/")[0] if "/" in model_id else "unknown")
    if raw_response and len(raw_response) > 4096:
        raw_response = raw_response[:4096]

    # Phase 4 columns (trace_id, span_id, parent_span_id) added via migration 003
    conn = get_connection()
    conn.execute(
        "INSERT INTO cost_runs (run_id, run_type, label, model_id, started_at, finished_at, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'completed')",
        (rid, run_type, label, model_id, now, now),
    )
    conn.execute(
        "INSERT INTO cost_run_calls (run_id, sequence, provider, model, input_tokens, "
        "output_tokens, cache_read_tokens, cache_write_tokens, call_cost, latency_ms, raw_response) "
        "VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (rid, prov, model_id, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
         cost, latency_ms, raw_response),
    )
    conn.commit()
    conn.close()
    return rid
```

CLI adds flags: `--cache-read-tokens`, `--cache-write-tokens`, `--latency-ms`, `--provider`

**CLI command — `record`:**

```python
# Add to src/cost_intel/cli.py
from cost_intel.record import record_run

@app.command()
def record(
    model: str = typer.Option(..., "--model", "-m", help="Model ID (e.g., openai/gpt-4o)"),
    input_tokens: int = typer.Option(..., "--input-tokens", "-i", help="Input tokens"),
    output_tokens: int = typer.Option(..., "--output-tokens", "-o", help="Output tokens"),
    label: Optional[str] = typer.Option(None, "--label", "-l", help="Human-readable label"),
    cache_read_tokens: int = typer.Option(0, "--cache-read-tokens", help="Cache read tokens"),
    cache_write_tokens: int = typer.Option(0, "--cache-write-tokens", help="Cache write tokens"),
    latency_ms: Optional[int] = typer.Option(None, "--latency-ms", help="Latency in ms"),
    provider: Optional[str] = typer.Option(None, "--provider", help="Provider (auto-detected if omitted)"),
):
    """Record a cost run manually."""
    # NOTE: trace_id/span_id/parent_span_id kwargs on record_run() are ignored
    # in Phase 1 — they become functional after migration 003 (Task 4.0) adds
    # the columns. This CLI does not expose them until Phase 4.
    run_id = record_run(
        model_id=model, input_tokens=input_tokens, output_tokens=output_tokens,
        label=label, cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens, latency_ms=latency_ms, provider=provider,
    )
    console.print(f"[green]✓[/green] Recorded run [bold]{run_id}[/bold]")
```

### Task 1.5: Reporting — `report --last 7d`, `trends`, `export`, `budget`

**KEY FIX:** Time-window filtering via `parse_window()`, budget uses `type='table'` (not `'name'`), subcommand structure.

```python
# src/cost_intel/budget.py
"""Budget tracking — set/status subcommands."""

from cost_intel.db import get_connection

_BUDGET_KEY = "budget_monthly"
_ALERT_KEY = "budget_alert_threshold"


def set_budget(monthly: float, alert_threshold: int = 80) -> None:
    conn = get_connection()
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (_BUDGET_KEY, str(monthly)))
    conn.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (_ALERT_KEY, str(alert_threshold)))
    conn.commit()
    conn.close()


def get_budget_status() -> dict:
    conn = get_connection()
    # FIX: config table is in migration 001 schema, but keep safe check
    table_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='config'"
    ).fetchone()
    if not table_exists:
        conn.close()
        return {"budget_set": False}
    # ... rest of budget calculation
```

CLI uses Typer sub-app:
```python
budget_app = typer.Typer(help="Budget management")

@budget_app.command("set")
def budget_set(monthly: float = typer.Option(...), alert: int = typer.Option(80)):
    set_budget(monthly, alert)
    console.print(f"[green]✓[/green] Budget set: ${monthly:.2f}/mo")

@budget_app.command("status")
def budget_status():
    status = get_budget_status()
    # ... display budget status table

app.add_typer(budget_app, name="budget")
```

**CLI command — `report`:**

```python
# Add to src/cost_intel/cli.py
from cost_intel.report import report_by_model, report_by_label, report_by_day
from cost_intel.duration import parse_window

@app.command()
def report(
    by_model: bool = typer.Option(False, "--by-model", help="Group by model"),
    by_label: bool = typer.Option(False, "--by-label", help="Group by label"),
    by_day: bool = typer.Option(False, "--by-day", help="Group by day"),
    last: str = typer.Option("7d", "--last", "-l", help="Time window (e.g. 7d, 30d, 1w)"),
):
    """Show cost report. Default: last 7 days summary."""
    from rich.table import Table
    days = parse_window(last)

    if by_model:
        results = report_by_model(days=days)
        table = Table(title=f"Cost by Model (last {days}d)")
        table.add_column("Model", style="cyan")
        table.add_column("Runs", justify="right")
        table.add_column("Total Cost", justify="right")
        table.add_column("Input Tokens", justify="right")
        table.add_column("Output Tokens", justify="right")
        for r in results:
            table.add_row(r["model_id"], str(r["total_runs"]),
                         f"${r['total_cost']:.4f}", str(r["total_input_tokens"]),
                         str(r["total_output_tokens"]))
    elif by_label:
        results = report_by_label(days=days)
        table = Table(title=f"Cost by Label (last {days}d)")
        table.add_column("Label", style="cyan")
        table.add_column("Runs", justify="right")
        table.add_column("Total Cost", justify="right")
        for r in results:
            table.add_row(r["label"] or "(none)", str(r["total_runs"]),
                         f"${r['total_cost']:.4f}")
    elif by_day:
        results = report_by_day(days=days)
        table = Table(title=f"Cost by Day (last {days}d)")
        table.add_column("Day (UTC)", style="cyan")
        table.add_column("Runs", justify="right")
        table.add_column("Total Cost", justify="right")
        for r in results:
            table.add_row(r["day"], str(r["total_runs"]),
                         f"${r['total_cost']:.4f}")
    else:
        results = report_by_model(days=days)
        total_runs = sum(r["total_runs"] for r in results)
        total_cost = sum(r["total_cost"] for r in results)
        table = Table(title=f"Cost Summary (last {days}d)")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_row("Total Runs", str(total_runs))
        table.add_row("Total Cost", f"${total_cost:.4f}")
    console.print(table)
```

### Task 1.6: Token Estimation — `cost-intel estimate`

```python
# src/cost_intel/estimate.py
import tiktoken
from cost_intel.pricing import get_pricing

def estimate_tokens(text: str, model: str = "gpt-4o") -> int:
    try:
        encoding = tiktoken.encoding_for_model(model.split("/")[-1] if "/" in model else model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

def estimate_cost(text: str, model_id: str, output_tokens_est: int = 500) -> dict:
    input_tokens = estimate_tokens(text, model_id)
    pricing = get_pricing(model_id)
    if not pricing:
        return {"input_tokens": input_tokens, "estimated_cost": None, "pricing_found": False}
    cost = (input_tokens / 1000) * (pricing["input_price_per_1k_tokens"] or 0)
    cost += (output_tokens_est / 1000) * (pricing["output_price_per_1k_tokens"] or 0)
    return {"input_tokens": input_tokens, "output_tokens_est": output_tokens_est,
            "estimated_cost": round(cost, 6), "pricing_found": True, "model": model_id}
```

**CLI command — `estimate`:**

```python
# Add to src/cost_intel/cli.py
from cost_intel.estimate import estimate_cost

@app.command()
def estimate(
    text: str = typer.Option(..., "--text", "-t", help="Input text to estimate"),
    model: str = typer.Option("openai/gpt-4o", "--model", "-m", help="Model ID"),
    output_tokens: int = typer.Option(500, "--output-tokens", "-o", help="Estimated output tokens"),
):
    """Estimate cost before making an API call."""
    result = estimate_cost(text, model, output_tokens)
    if result["pricing_found"]:
        console.print(f"Input tokens: [bold]{result['input_tokens']}[/bold]")
        console.print(f"Est output tokens: [bold]{result['output_tokens_est']}[/bold]")
        console.print(f"Estimated cost: [bold]${result['estimated_cost']:.6f}[/bold]")
    else:
        console.print(f"[yellow]No pricing found for {model}[/yellow]")
        console.print(f"Input tokens: {result['input_tokens']}")
```

### Task 1.7: Ingest API Responses — cache token extraction

**KEY FIX:** Extracts provider-specific cache token fields.

```python
# src/cost_intel/ingest.py
import json
from pathlib import Path
from typing import Optional
from cost_intel.record import record_run


def _extract_cache_tokens(usage: dict, provider: str) -> tuple[int, int]:
    if provider == "openai":
        details = usage.get("prompt_tokens_details", {})
        return details.get("cached_tokens", 0), 0
    elif provider == "anthropic":
        return usage.get("cache_read_input_tokens", 0), usage.get("cache_creation_input_tokens", 0)
    return usage.get("cache_read_tokens", 0), usage.get("cache_write_tokens", 0)


def ingest_jsonl(file_path: str, format: str = "openrouter",
                 label: Optional[str] = None, days: Optional[int] = None) -> int:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    count = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if format == "openrouter":
                model = record.get("model", "unknown")
                usage = record.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                provider = model.split("/")[0] if "/" in model else "unknown"
                cache_read, cache_write = _extract_cache_tokens(usage, provider)
            else:
                model = record.get("model", "unknown")
                input_tokens = record.get("input_tokens", 0)
                output_tokens = record.get("output_tokens", 0)
                cache_read = record.get("cache_read_tokens", 0)
                cache_write = record.get("cache_write_tokens", 0)
            raw_response = json.dumps(record)[:4096]
            record_run(model_id=model, input_tokens=input_tokens, output_tokens=output_tokens,
                     label=label, cache_read_tokens=cache_read, cache_write_tokens=cache_write,
                     raw_response=raw_response)
            count += 1
    return count
```

**CLI command — `ingest-api-responses`:**

```python
# Add to src/cost_intel/cli.py
from cost_intel.ingest import ingest_jsonl

@app.command(name="ingest-api-responses")
def ingest_cmd(
    file: str = typer.Argument(..., help="Path to JSONL file"),
    format: str = typer.Option("openrouter", "--format", "-f", help="Input format"),
    label: Optional[str] = typer.Option(None, "--label", "-l", help="Label for all runs"),
):
    """Ingest API responses from a JSONL file."""
    count = ingest_jsonl(file, format=format, label=label)
    console.print(f"[green]✓[/green] Ingested [bold]{count}[/bold] records from {file}")
```

### Task 1.8: Tests + CI + PyPI Publish

- CI workflow includes `ruff format --check`
- `pyproject.toml` has full PyPI metadata
- Integration tests in `tests/integration/` covering invoice reconciliation and CPQP ordering:

```python
# tests/integration/test_invoice_reconciliation.py
"""Integration test: reconcile ingested costs against a fixture invoice."""
import json, pytest
from pathlib import Path

def test_cost_totals_match_fixture(tmp_cost_intel_home, tmp_path):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.ingest import ingest_jsonl

    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)

    fixture = tmp_path / "fixture.jsonl"
    records = [
        {"model": "openai/gpt-4o", "usage": {"prompt_tokens": 100, "completion_tokens": 50}},
        {"model": "openai/gpt-4o", "usage": {"prompt_tokens": 200, "completion_tokens": 100}},
    ]
    fixture.write_text("\n".join(json.dumps(r) for r in records))
    count = ingest_jsonl(str(fixture))
    assert count == 2

    from cost_intel.report import report_by_model
    results = report_by_model(days=30)
    assert len(results) == 1
    assert abs(results[0]["total_cost"] - 2.25) < 0.01
```

```python
# tests/integration/test_cpqp_ordering.py
"""Integration test: verify CPQP ordering matches intuition."""
import pytest

def test_cpqp_ordering_expensive_low_quality(tmp_cost_intel_home):
    """An expensive low-quality run should have higher CPQP than cheap high-quality."""
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    from cost_intel.quality import import_score
    from cost_intel.quality import get_cpqp

    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)

    cheap_good = record_run("openai/gpt-4o", 10, 5)
    import_score(cheap_good, score=0.95, source="test")

    expensive_bad = record_run("openai/gpt-4o", 10000, 5000)
    import_score(expensive_bad, score=0.05, source="test")

    cpqp_cheap = get_cpqp(cheap_good)
    cpqp_expensive = get_cpqp(expensive_bad)

    assert cpqp_expensive["cpqp"] > cpqp_cheap["cpqp"]
```

### Task 1.9: Dogfood on Hermes Cron

- Run `scripts/dogfood.sh` to ingest real Hermes logs
- Verify cost totals match OpenRouter dashboard
- Commit: `feat: Phase 1 complete — cost-only foundation with migration framework`

**`scripts/dogfood.sh` contents:**

```bash
#!/usr/bin/env bash
# scripts/dogfood.sh — Ingest real Hermes cron logs and verify costs
set -euo pipefail

echo "=== cost-intel dogfood test ==="

# Ingest recent OpenRouter logs if available
LOG_DIR="${HOME}/.hermes/logs"
if [ -d "$LOG_DIR" ]; then
    find "$LOG_DIR" -name "*.jsonl" -mtime -1 | head -5 | while read f; do
        echo "Ingesting: $f"
        cost-intel ingest-api-responses "$f" --format openrouter --label "dogfood-$(basename $f)"
    done
fi

echo ""
echo "=== Cost Report (last 7 days) ==="
cost-intel report --last 7d --by-model

echo ""
echo "=== Budget Status ==="
cost-intel budget status

echo ""
echo "=== Dogfood complete ==="
```
# Phase 2: Quality Correlation (Weeks 4-6) — REVISED

> **Deliverable:** CPQP metric + waste detection. Import quality scores from any source.
> **Precondition:** Phase 1 complete (cost-only CLI working, migrations framework in place).
> **Scope of this revision:** All Droid audit findings affecting Phase 2 are addressed here:
> - CRITICAL: CPQP percentile-based ratings (A/B/C/D/F) now core to the design
> - CRITICAL: `get_waste_index()` SQL rewritten with CTE, no aggregates in WHERE
> - CRITICAL: `optimize` CLI bool flag shadowing fixed
> - CRITICAL: Schema migration 002 added (Task 2.0)
> - HIGH: Eval Harness + Braintrust adapters fully implemented (not stubs)
> - HIGH: CSV `--mapping` JSON column mapping added
> - HIGH: `combined_score` weighted aggregation computed in `import_score()`
> - HIGH: `--target-cpqp` behavior implemented
> - HIGH: Time-window filtering (`--last`/`--days`) added to cpqp command
> - MEDIUM: `Optional` imports added to all modules
> - MEDIUM: Week-over-week CPQP trend (`get_cpqp_trend()`)
> - MEDIUM: Model Efficiency Delta in `compare_models`

---

## Task 2.0: Schema Migration — `quality_scores` table + CPQP view with percentile ratings

**Objective:** Add migration 002 that creates the `quality_scores` table, updates the `cost_run_cpqp` view with percentile-based ratings, and establishes the migration runner pattern that all subsequent phases depend on.

**This task must run before any other Phase 2 task.** It creates the schema that everything else assumes.

**Files:**
- Create: `src/cost_intel/migrations/001_initial.sql`
- Create: `src/cost_intel/migrations/002_add_quality.sql`
- Create: `src/cost_intel/migration_runner.py`
- Modify: `src/cost_intel/db.py` (add migration runner into `init_db()`)
- Test: `tests/test_migrations.py`

### Step 1: Write failing test

```python
# tests/test_migrations.py
import pytest
from cost_intel.migration_runner import get_current_version, apply_pending_migrations

def test_initial_version_is_zero(tmp_cost_intel_home):
    from cost_intel.db import init_db
    init_db()
    # Before any migrations applied, version should be 0
    ver = get_current_version()
    assert ver == 0

def test_migration_001_creates_base_tables(tmp_cost_intel_home):
    from cost_intel.db import init_db, get_connection
    init_db()
    apply_pending_migrations()
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {r["name"] for r in tables}
    assert "cost_runs" in table_names
    assert "cost_run_calls" in table_names
    assert "model_pricing" in table_names
    assert "schema_version" in table_names
    conn.close()

def test_migration_002_creates_quality_tables(tmp_cost_intel_home):
    from cost_intel.db import init_db, get_connection
    init_db()
    apply_pending_migrations()
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {r["name"] for r in tables}
    assert "quality_scores" in table_names
    # Check CPQP view exists
    views = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view'"
    ).fetchall()
    view_names = {r["name"] for r in views}
    assert "cost_run_cpqp" in view_names
    conn.close()

def test_migration_002_version_tracking(tmp_cost_intel_home):
    from cost_intel.db import init_db
    init_db()
    apply_pending_migrations()
    ver = get_current_version()
    assert ver == 2

def test_idempotent_migration(tmp_cost_intel_home):
    """Running migrations twice must not error or duplicate."""
    from cost_intel.db import init_db
    init_db()
    apply_pending_migrations()
    apply_pending_migrations()  # Must be a no-op
    ver = get_current_version()
    assert ver == 2
```

### Step 2: Run test to verify failure

```bash
pytest tests/test_migrations.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'cost_intel.migration_runner'`

### Step 3: Create migration files

```sql
-- src/cost_intel/migrations/001_initial.sql
-- Phase 1 schema (cost_runs, cost_run_calls, model_pricing, config)
-- This migration is idempotent: uses IF NOT EXISTS throughout.

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS model_pricing (
    model_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    input_price_per_1k_tokens REAL,
    output_price_per_1k_tokens REAL,
    cache_read_price_per_1k_tokens REAL DEFAULT NULL,
    cache_write_price_per_1k_tokens REAL DEFAULT NULL,
    effective_date TEXT NOT NULL DEFAULT (date('now')),
    is_current BOOLEAN DEFAULT 1,
    source TEXT DEFAULT 'openrouter',
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cost_runs (
    run_id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL DEFAULT 'api_call',
    label TEXT,
    model_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT DEFAULT 'completed',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cost_runs_model ON cost_runs(model_id);
CREATE INDEX IF NOT EXISTS idx_cost_runs_date ON cost_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_cost_runs_type ON cost_runs(run_type);
CREATE INDEX IF NOT EXISTS idx_cost_runs_label ON cost_runs(label);

CREATE TABLE IF NOT EXISTS cost_run_calls (
    call_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES cost_runs(run_id),
    sequence INTEGER NOT NULL DEFAULT 0,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read_tokens INTEGER DEFAULT 0,
    cache_write_tokens INTEGER DEFAULT 0,
    call_cost REAL NOT NULL,
    latency_ms INTEGER,
    raw_response TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_calls_run ON cost_run_calls(run_id);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

```sql
-- src/cost_intel/migrations/002_add_quality.sql
-- Phase 2 schema: quality_scores table + CPQP view with percentile ratings.

CREATE TABLE IF NOT EXISTS quality_scores (
    score_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES cost_runs(run_id),
    source TEXT NOT NULL,
    source_run_id TEXT,
    combined_score REAL NOT NULL CHECK(combined_score >= 0.0 AND combined_score <= 1.0),
    eval_dimensions TEXT,
    eval_weights TEXT,
    notes TEXT,
    imported_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_quality_run ON quality_scores(run_id);
CREATE INDEX IF NOT EXISTS idx_quality_source ON quality_scores(source);
CREATE INDEX IF NOT EXISTS idx_quality_score ON quality_scores(combined_score);

-- Drop and recreate the CPQP view so the new percentile-based rating
-- replaces any prior version. DROP + CREATE (not IF NOT EXISTS) ensures
-- view definition is always current after migration.
DROP VIEW IF EXISTS cost_run_cpqp;

CREATE VIEW cost_run_cpqp AS
SELECT
    cr.run_id,
    cr.label,
    cr.model_id,
    cr.started_at,
    SUM(crc.call_cost) AS total_cost,
    COUNT(crc.call_id) AS call_count,
    SUM(crc.input_tokens) AS total_input_tokens,
    SUM(crc.output_tokens) AS total_output_tokens,
    qs.combined_score,
    qs.source AS quality_source,
    CASE
        WHEN qs.combined_score IS NULL THEN NULL
        ELSE ROUND(SUM(crc.call_cost) / MAX(qs.combined_score, 0.01), 4)
    END AS cpqp,
    CASE
        WHEN qs.combined_score IS NULL THEN 'N/A'
        WHEN PERCENT_RANK() OVER (
            ORDER BY SUM(crc.call_cost) / MAX(qs.combined_score, 0.01)
        ) <= 0.25 THEN 'A'
        WHEN PERCENT_RANK() OVER (
            ORDER BY SUM(crc.call_cost) / MAX(qs.combined_score, 0.01)
        ) <= 0.50 THEN 'B'
        WHEN PERCENT_RANK() OVER (
            ORDER BY SUM(crc.call_cost) / MAX(qs.combined_score, 0.01)
        ) <= 0.75 THEN 'C'
        WHEN PERCENT_RANK() OVER (
            ORDER BY SUM(crc.call_cost) / MAX(qs.combined_score, 0.01)
        ) <= 0.90 THEN 'D'
        ELSE 'F'
    END AS rating
FROM cost_runs cr
LEFT JOIN cost_run_calls crc ON cr.run_id = crc.run_id
LEFT JOIN quality_scores qs ON cr.run_id = qs.run_id
GROUP BY cr.run_id;
```

### Step 4: Write migration runner

```python
# src/cost_intel/migration_runner.py
"""Schema migration runner — numbered SQL files, version tracking."""

import os
import sqlite3
from pathlib import Path
from typing import Optional

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _get_migration_files() -> list[tuple[int, Path]]:
    """Return sorted list of (version_number, path) for all .sql files."""
    if not _MIGRATIONS_DIR.exists():
        return []
    files = []
    for f in _MIGRATIONS_DIR.glob("*.sql"):
        try:
            ver = int(f.stem.split("_")[0])
            files.append((ver, f))
        except (ValueError, IndexError):
            continue
    return sorted(files, key=lambda x: x[0])


def get_current_version(conn: Optional[sqlite3.Connection] = None) -> int:
    """Return the highest applied migration version, or 0."""
    if conn is None:
        from cost_intel.db import get_connection
        conn = get_connection()
        should_close = True
    else:
        should_close = False
    try:
        row = conn.execute(
            "SELECT MAX(version) as ver FROM schema_version"
        ).fetchone()
        return row["ver"] if row and row["ver"] is not None else 0
    except sqlite3.OperationalError:
        # schema_version table doesn't exist yet
        return 0
    finally:
        if should_close:
            conn.close()


def apply_pending_migrations(conn: Optional[sqlite3.Connection] = None) -> int:
    """Apply all pending migrations in order. Returns new version."""
    if conn is None:
        from cost_intel.db import get_connection
        conn = get_connection()
        should_close = True
    else:
        should_close = False

    try:
        # Ensure schema_version table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()

        current = get_current_version(conn)
        applied = current

        for ver, path in _get_migration_files():
            if ver <= current:
                continue
            sql = path.read_text()
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (ver,)
            )
            conn.commit()
            applied = ver

        return applied
    finally:
        if should_close:
            conn.close()
```

### Step 5: Update db.py to run migrations on init

Modify `src/cost_intel/db.py` — replace the old `_SCHEMA` string approach with migration-based initialization:

```python
# In src/cost_intel/db.py, add at top:
from cost_intel.migration_runner import apply_pending_migrations

# In init_db(), after opening the connection, call:
def init_db(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Initialize the database, running any pending migrations."""
    conn = get_connection(db_path)
    apply_pending_migrations(conn)
    return conn
```

### Step 6: Run test to verify pass

```bash
pytest tests/test_migrations.py -v
```
Expected: 5 passed

### Step 7: Commit

```bash
git add src/cost_intel/migrations/ src/cost_intel/migration_runner.py src/cost_intel/db.py tests/test_migrations.py
git commit -m "feat: schema migration framework — migration 002 adds quality_scores + percentile CPQP view"
```

---

## Task 2.1: Quality Score Import — `quality.py` + Adapters + `import-scores` CLI

**Objective:** Implement `quality.py` with `import_score()`, `compute_combined_score()`, CSV import with `--mapping`, and fully-implemented Eval Harness + Braintrust adapters. Wire all three sources into `cost-intel import-scores`.

**Files:**
- Create: `src/cost_intel/quality.py`
- Create: `src/cost_intel/adapters/__init__.py`
- Create: `src/cost_intel/adapters/eval_harness.py`
- Create: `src/cost_intel/adapters/braintrust.py`
- Modify: `src/cost_intel/cli.py` (add `import-scores` command)
- Test: `tests/test_quality.py`
- Test: `tests/test_adapters.py`

### Step 1: Write failing test

```python
# tests/test_quality.py
import pytest
from cost_intel.quality import (
    import_score,
    import_scores_csv,
    get_cpqp,
    get_all_cpqp,
    get_waste_runs,
    compute_combined_score,
)

def test_import_score_basic(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.record import record_run
    init_db()
    run_id = record_run("openai/gpt-4o", 100, 50, label="test")
    import_score(run_id, score=0.85, source="test")
    row = get_cpqp(run_id)
    assert row is not None
    assert row["combined_score"] == 0.85

def test_import_score_clamps_range(tmp_cost_intel_home):
    """Score must be clamped to [0.0, 1.0]."""
    from cost_intel.db import init_db
    from cost_intel.record import record_run
    init_db()
    run_id = record_run("openai/gpt-4o", 100, 50)
    import_score(run_id, score=1.5, source="test")
    row = get_cpqp(run_id)
    assert row["combined_score"] == 1.0

def test_cpqp_division_by_zero_guard(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 1000, 500)
    import_score(run_id, score=0.0, source="test")
    cpqp = get_cpqp(run_id)
    # Cost=7.5, score=0 → FLOOR=0.01 → CPQP=750.0
    assert cpqp["cpqp"] == 750.0

def test_compute_combined_score_equal_weights():
    dims = {"faithfulness": 0.8, "task_completion": 0.9}
    result = compute_combined_score(dims)
    assert abs(result - 0.85) < 0.001

def test_compute_combined_score_custom_weights():
    dims = {"faithfulness": 0.8, "task_completion": 0.9}
    weights = {"faithfulness": 0.3, "task_completion": 0.7}
    result = compute_combined_score(dims, weights)
    expected = 0.3 * 0.8 + 0.7 * 0.9
    assert abs(result - expected) < 0.001

def test_compute_combined_score_weights_normalized():
    """Weights that don't sum to 1.0 are normalized."""
    dims = {"a": 0.5, "b": 0.5}
    weights = {"a": 2.0, "b": 2.0}  # sum=4, should normalize to 0.5/0.5
    result = compute_combined_score(dims, weights)
    assert abs(result - 0.5) < 0.001

def test_import_score_with_dimensions_computes_combined(tmp_cost_intel_home):
    """When eval_dimensions supplied and score is None, auto-compute combined."""
    from cost_intel.db import init_db
    from cost_intel.record import record_run
    init_db()
    run_id = record_run("openai/gpt-4o", 100, 50)
    dims = {"faithfulness": 0.8, "task_completion": 0.9}
    import_score(run_id, score=None, source="eval_harness", eval_dimensions=dims)
    row = get_cpqp(run_id)
    assert abs(row["combined_score"] - 0.85) < 0.001

def test_import_scores_csv_with_mapping(tmp_cost_intel_home, tmp_path):
    from cost_intel.db import init_db
    from cost_intel.record import record_run
    init_db()
    run_id = record_run("openai/gpt-4o", 100, 50, label="test")
    csv_file = tmp_path / "scores.csv"
    csv_file.write_text(f"id,quality\n{run_id},0.75\n")
    count = import_scores_csv(
        str(csv_file),
        run_id_col="id",
        score_col="quality",
        source="csv",
    )
    assert count == 1
    row = get_cpqp(run_id)
    assert row["combined_score"] == 0.75

def test_get_waste_runs_uses_percentile_rating(tmp_cost_intel_home):
    """Waste runs = rating D or F (top 20% CPQP), NOT cpqp > 0.50."""
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    # Create 10 runs: 9 cheap+high-quality, 1 expensive+low-quality
    for i in range(9):
        rid = record_run("openai/gpt-4o", 10, 5, label=f"good-{i}")
        import_score(rid, score=0.95, source="test")
    # The expensive low-quality run should be rated D or F
    expensive_run = record_run("openai/gpt-4o", 10000, 5000, label="waste")
    import_score(expensive_run, score=0.05, source="test")
    waste = get_waste_runs()
    # Should include the expensive run (rating D or F)
    waste_ids = {w["run_id"] for w in waste}
    assert expensive_run in waste_ids

def test_get_all_cpqp_includes_rating(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50)
    import_score(run_id, score=0.85, source="test")
    results = get_all_cpqp()
    assert len(results) >= 1
    assert "rating" in results[0]
    assert results[0]["rating"] in ("A", "B", "C", "D", "F")
```

```python
# tests/test_adapters.py
import pytest
from unittest.mock import patch, MagicMock

def test_eval_harness_adapter(tmp_cost_intel_home, tmp_path):
    """Eval Harness adapter reads from SQLite and calls import_score."""
    from cost_intel.db import init_db
    from cost_intel.record import record_run
    from cost_intel.adapters.eval_harness import import_from_eval_harness
    init_db()
    run_id = record_run("openai/gpt-4o", 100, 50, label="test")
    # Create a fake eval-harness DB
    import sqlite3
    eval_db = tmp_path / "eval.db"
    conn = sqlite3.connect(str(eval_db))
    conn.execute(
        "CREATE TABLE results (run_id TEXT, score REAL, source TEXT)"
    )
    conn.execute(
        "INSERT INTO results VALUES (?, ?, ?)",
        (run_id, 0.82, "eval_harness"),
    )
    conn.commit()
    conn.close()
    count = import_from_eval_harness(str(eval_db))
    assert count == 1

def test_braintrust_adapter(tmp_cost_intel_home):
    """Braintrust adapter calls HTTPX GET and imports scores."""
    from cost_intel.db import init_db
    from cost_intel.record import record_run
    from cost_intel.adapters.braintrust import import_from_braintrust
    init_db()
    run_id = record_run("openai/gpt-4o", 100, 50, label="test")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": [
            {"run_id": run_id, "scores": {"quality": 0.78}}
        ]
    }
    with patch("httpx.get", return_value=mock_response):
        count = import_from_braintrust(
            api_key="bt-test-key",
            project_id="test-project",
        )
    assert count == 1
```

### Step 2: Run test to verify failure

```bash
pytest tests/test_quality.py tests/test_adapters.py -v
```
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Write `quality.py`

```python
# src/cost_intel/quality.py
"""Quality score import, CPQP calculation, and waste detection."""

import csv
import json
from typing import Optional

from cost_intel.db import get_connection


def compute_combined_score(
    dimensions: dict[str, float],
    weights: Optional[dict[str, float]] = None,
) -> float:
    """Compute weighted combined score from multiple eval dimensions.

    Args:
        dimensions: Mapping of dimension name → score (0.0-1.0).
        weights: Mapping of dimension name → weight. If None, equal
            weights are used. Weights are normalized to sum to 1.0.

    Returns:
        Combined score in [0.0, 1.0].
    """
    if not dimensions:
        return 0.0

    if weights is None:
        n = len(dimensions)
        weights = {k: 1.0 / n for k in dimensions}

    # Normalize weights to sum to 1.0
    total_w = sum(weights.get(k, 0.0) for k in dimensions)
    if total_w <= 0:
        return 0.0

    combined = sum(
        dimensions[k] * (weights.get(k, 0.0) / total_w)
        for k in dimensions
    )
    return max(0.0, min(1.0, combined))


def import_score(
    run_id: str,
    score: Optional[float],
    source: str,
    source_run_id: Optional[str] = None,
    eval_dimensions: Optional[dict] = None,
    eval_weights: Optional[dict] = None,
    notes: Optional[str] = None,
) -> None:
    """Import a quality score for a run.

    If eval_dimensions is supplied and score is None, the combined_score
    is auto-computed from the dimensions using compute_combined_score().
    """
    if score is None and eval_dimensions:
        score = compute_combined_score(eval_dimensions, eval_weights)
    elif score is None:
        score = 0.0

    # Clamp to valid range
    score = max(0.0, min(1.0, score))

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO quality_scores
            (run_id, source, source_run_id, combined_score,
             eval_dimensions, eval_weights, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            source,
            source_run_id,
            score,
            json.dumps(eval_dimensions) if eval_dimensions else None,
            json.dumps(eval_weights) if eval_weights else None,
            notes,
        ),
    )
    conn.commit()
    conn.close()


def import_scores_csv(
    file_path: str,
    run_id_col: str = "run_id",
    score_col: str = "score",
    source: str = "csv",
    mapping: Optional[dict] = None,
) -> int:
    """Import quality scores from a CSV file.

    Args:
        file_path: Path to CSV file.
        run_id_col: Column name for run_id.
        score_col: Column name for score.
        source: Source label.
        mapping: Optional dict to remap column names.
            e.g. {"run_id": "id", "score": "quality"} means
            the CSV has columns "id" and "quality" which map to
            run_id_col="run_id" and score_col="score".
    """
    if mapping:
        run_id_col = mapping.get("run_id", run_id_col)
        score_col = mapping.get("score", score_col)

    conn = get_connection()
    count = 0
    with open(file_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            run_id = row.get(run_id_col, "")
            try:
                score = float(row.get(score_col, 0))
            except (ValueError, TypeError):
                continue
            if not run_id:
                continue
            conn.execute(
                """
                INSERT INTO quality_scores (run_id, source, combined_score)
                VALUES (?, ?, ?)
                """,
                (run_id, source, max(0.0, min(1.0, score))),
            )
            count += 1
    conn.commit()
    conn.close()
    return count


def get_cpqp(run_id: str) -> Optional[dict]:
    """Get CPQP for a specific run."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM cost_run_cpqp WHERE run_id = ?", (run_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_cpqp(
    limit: Optional[int] = None,
    min_rating: Optional[str] = None,
) -> list[dict]:
    """Get CPQP for all runs that have quality scores.

    Args:
        limit: Maximum number of rows to return.
        min_rating: If set, only return runs with this rating or worse.
            E.g. "D" returns D and F rated runs.
    """
    conn = get_connection()
    query = "SELECT * FROM cost_run_cpqp WHERE combined_score IS NOT NULL"
    params: list = []

    if min_rating:
        rating_order = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
        threshold = rating_order.get(min_rating, 4)
        allowed = [r for r, v in rating_order.items() if v >= threshold]
        placeholders = ",".join("?" for _ in allowed)
        query += f" AND rating IN ({placeholders})"
        params.extend(allowed)

    query += " ORDER BY cpqp DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_waste_runs() -> list[dict]:
    """Get runs with rating D or F (inefficient spending).

    Uses the percentile-based rating from the CPQP view, NOT a hardcoded
    dollar threshold. D = 75th-90th percentile, F = top 10%.
    """
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM cost_run_cpqp
        WHERE rating IN ('D', 'F')
        ORDER BY cpqp DESC
        """
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

### Step 4: Write adapter — Eval Harness

```python
# src/cost_intel/adapters/__init__.py
"""Quality score import adapters."""
```

```python
# src/cost_intel/adapters/eval_harness.py
"""Eval Harness adapter — import quality scores from Eval Harness SQLite DB."""

import sqlite3
from typing import Optional

from cost_intel.quality import import_score


def import_from_eval_harness(
    db_path: str,
    source: str = "eval_harness",
    run_id_column: str = "run_id",
    score_column: str = "score",
) -> int:
    """Import quality scores from an Eval Harness SQLite database.

    Opens the Eval Harness DB at db_path, reads score rows, and calls
    import_score() for each one. Returns count of scores imported.

    Args:
        db_path: Path to the Eval Harness SQLite database file.
        source: Source label for imported scores.
        run_id_column: Column name for run_id in the source DB.
        score_column: Column name for score in the source DB.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Try common Eval Harness table/column names
        rows = conn.execute(
            f"SELECT {run_id_column}, {score_column} FROM results"
        ).fetchall()
    except sqlite3.OperationalError:
        # Fallback: try 'eval_results' table
        try:
            rows = conn.execute(
                f"SELECT {run_id_column}, {score_column} FROM eval_results"
            ).fetchall()
        except sqlite3.OperationalError:
            conn.close()
            return 0
    finally:
        conn.close()

    count = 0
    for row in rows:
        run_id = str(row[run_id_column]) if row[run_id_column] else None
        score = float(row[score_column]) if row[score_column] is not None else None
        if run_id and score is not None:
            import_score(run_id=run_id, score=score, source=source)
            count += 1
    return count
```

### Step 5: Write adapter — Braintrust

```python
# src/cost_intel/adapters/braintrust.py
"""Braintrust adapter — import quality scores via Braintrust REST API."""

from typing import Optional

import httpx

from cost_intel.quality import import_score


def import_from_braintrust(
    api_key: str,
    project_id: str,
    experiment_id: Optional[str] = None,
    source: str = "braintrust",
    base_url: str = "https://api.braintrust.dev/v1",
) -> int:
    """Import quality scores from Braintrust.

    Fetches experiment data from Braintrust REST API and imports
    scores for each run. Returns count of scores imported.

    Args:
        api_key: Braintrust API key.
        project_id: Braintrust project ID.
        experiment_id: Optional experiment ID. If None, fetches all
            experiments in the project.
        source: Source label for imported scores.
        base_url: Braintrust API base URL.
    """
    headers = {"Authorization": f"Bearer {api_key}"}
    count = 0

    with httpx.Client(base_url=base_url, headers=headers, timeout=30) as client:
        if experiment_id:
            exp_ids = [experiment_id]
        else:
            resp = client.get(f"/projects/{project_id}/experiments")
            resp.raise_for_status()
            experiments = resp.json().get("data", [])
            exp_ids = [exp["id"] for exp in experiments]

        for eid in exp_ids:
            resp = client.get(f"/experiments/{eid}/events")
            resp.raise_for_status()
            events = resp.json().get("data", [])

            for event in events:
                run_id = event.get("run_id") or event.get("id")
                scores = event.get("scores", {})
                if not run_id or not scores:
                    continue
                # Use the first numeric score or a "quality" key
                score_val = scores.get("quality") or scores.get("score")
                if score_val is not None:
                    import_score(
                        run_id=str(run_id),
                        score=float(score_val),
                        source=source,
                        eval_dimensions=scores if len(scores) > 1 else None,
                    )
                    count += 1

    return count
```

### Step 6: Update cli.py — `import-scores` command

Add to `src/cost_intel/cli.py`:

```python
import json as _json
from cost_intel.quality import import_scores_csv, get_all_cpqp, get_waste_runs
from cost_intel.adapters.eval_harness import import_from_eval_harness
from cost_intel.adapters.braintrust import import_from_braintrust


@app.command(name="import-scores")
def import_scores_cmd(
    source: str = typer.Option(..., "--source", "-s",
        help="Source: csv, eval-harness, braintrust"),
    file: str = typer.Option(None, "--file", "-f",
        help="CSV file path (for csv source)"),
    db_path: str = typer.Option(None, "--db-path",
        help="SQLite DB path (for eval-harness source)"),
    api_key: str = typer.Option(None, "--api-key",
        help="API key (for braintrust source)"),
    project_id: str = typer.Option(None, "--project-id",
        help="Project ID (for braintrust source)"),
    mapping: str = typer.Option(None, "--mapping",
        help='JSON column mapping, e.g. \'{"run_id": "id", "score": "quality"}\''),
):
    """Import quality scores from an external source."""
    if source == "csv" and file:
        mapping_dict = _json.loads(mapping) if mapping else None
        count = import_scores_csv(file, source="csv", mapping=mapping_dict)
        console.print(f"[green]✓[/green] Imported [bold]{count}[/bold] scores from {file}")
    elif source == "eval-harness" and db_path:
        count = import_from_eval_harness(db_path)
        console.print(f"[green]✓[/green] Imported [bold]{count}[/bold] scores from Eval Harness")
    elif source == "braintrust" and api_key:
        count = import_from_braintrust(api_key=api_key, project_id=project_id or "")
        console.print(f"[green]✓[/green] Imported [bold]{count}[/bold] scores from Braintrust")
    else:
        console.print("[red]Error:[/red] insufficient arguments for source "
                       f"'{source}'. Check --help for required flags.")
        raise typer.Exit(1)
```

### Step 7: Run test to verify pass

```bash
pytest tests/test_quality.py tests/test_adapters.py -v
```
Expected: 12 passed

### Step 8: Commit

```bash
git add src/cost_intel/quality.py src/cost_intel/adapters/ tests/test_quality.py tests/test_adapters.py src/cost_intel/cli.py
git commit -m "feat: quality score import — adapters (eval-harness, braintrust, csv) + import-scores CLI"
```

---

## Task 2.2: CPQP Report + Waste CLI — `cost-intel cpqp` and `cost-intel waste`

**Objective:** Implement the `cpqp` and `waste` CLI commands with percentile-based ratings, time-window filtering (`--last`/`--days`), and rating column display.

**Files:**
- Modify: `src/cost_intel/cli.py`
- Test: `tests/test_cli_cpqp.py`

### Step 1: Write failing test

```python
# tests/test_cli_cpqp.py
import pytest
from typer.testing import CliRunner
from cost_intel.cli import app

runner = CliRunner()

def test_cpqp_shows_rating_column(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    from cost_intel.quality import import_score
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50)
    import_score(run_id, score=0.85, source="test")
    result = runner.invoke(app, ["cpqp"])
    assert result.exit_code == 0
    assert "Rating" in result.output or "rating" in result.output.lower()

def test_cpqp_waste_only_flag(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    from cost_intel.quality import import_score
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    # Create 10 runs so percentile is meaningful
    for i in range(9):
        rid = record_run("openai/gpt-4o", 10, 5, label=f"good-{i}")
        import_score(rid, score=0.95, source="test")
    expensive = record_run("openai/gpt-4o", 10000, 5000, label="waste")
    import_score(expensive, score=0.05, source="test")
    result = runner.invoke(app, ["cpqp", "--waste-only"])
    assert result.exit_code == 0
    assert "waste" in result.output.lower() or "D" in result.output or "F" in result.output

def test_waste_command_uses_percentile(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    from cost_intel.quality import import_score
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    for i in range(9):
        rid = record_run("openai/gpt-4o", 10, 5, label=f"good-{i}")
        import_score(rid, score=0.95, source="test")
    expensive = record_run("openai/gpt-4o", 10000, 5000, label="waste")
    import_score(expensive, score=0.05, source="test")
    result = runner.invoke(app, ["waste"])
    assert result.exit_code == 0
    # Should NOT contain "$0.50" (old hardcoded threshold)
    assert "0.50" not in result.output

def test_cpqp_last_flag_parses_duration(tmp_cost_intel_home):
    """--last 7d must not crash with type error."""
    result = runner.invoke(app, ["cpqp", "--last", "7d"])
    assert "not a valid integer" not in result.output
    assert result.exit_code == 0
```

### Step 2: Run test to verify failure

```bash
pytest tests/test_cli_cpqp.py -v
```
Expected: FAIL — commands not yet implemented

### Step 3: Import the canonical duration parser

Add near the top of `src/cost_intel/cli.py`:

```python
from cost_intel.duration import parse_window
```

The canonical `parse_window` lives in `src/cost_intel/duration.py` (Task 3.0,
tested in `tests/test_duration.py`). Do NOT define a local `_parse_window`
helper — all modules must import from `cost_intel.duration`.

### Step 4: Update cli.py — `cpqp` and `waste` commands

Replace the old `cpqp` command and add `waste`:

```python
@app.command()
def cpqp(
    waste_only: bool = typer.Option(False, "--waste-only",
        help="Show only D/F rated (inefficient) runs"),
    last: str = typer.Option(None, "--last",
        help="Time window (e.g., 7d, 30d, 12h). Default: all time"),
    by_model: bool = typer.Option(False, "--by-model",
        help="Group results by model"),
):
    """Show cost-per-quality-point (CPQP) report with percentile ratings."""
    from rich.table import Table

    # Build query
    if waste_only:
        results = get_waste_runs()
        title = "Waste Runs (Rating D or F)"
    else:
        results = get_all_cpqp()
        title = "Cost-Per-Quality-Point (CPQP)"

    # Apply time filter
    if last:
        days = parse_window(last)
        cutoff = f"-{days} days"
        conn = get_connection()
        filtered_ids = {
            r["run_id"] for r in conn.execute(
                "SELECT run_id FROM cost_runs WHERE started_at >= datetime('now', ?)",
                (cutoff,),
            ).fetchall()
        }
        conn.close()
        results = [r for r in results if r["run_id"] in filtered_ids]
        title += f" — last {last}"

    table = Table(title=title)
    table.add_column("Run ID", style="cyan", max_width=12)
    table.add_column("Label", max_width=20)
    table.add_column("Model", max_width=25)
    table.add_column("Cost", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("CPQP", justify="right")
    table.add_column("Rating", justify="right")
    for r in results:
        rating = r.get("rating", "N/A")
        rating_style = {
            "A": "green", "B": "bright_green", "C": "yellow",
            "D": "red", "F": "bold red", "N/A": "dim",
        }.get(rating, "")
        table.add_row(
            r["run_id"][:8],
            r["label"] or "",
            r["model_id"] or "",
            f"${r['total_cost']:.4f}",
            f"{r['combined_score']:.2f}" if r["combined_score"] is not None else "N/A",
            f"${r['cpqp']:.4f}" if r["cpqp"] is not None else "N/A",
            f"[{rating_style}]{rating}[/{rating_style}]" if rating_style else rating,
        )
    console.print(table)


@app.command()
def waste():
    """Show waste analysis — runs with D or F efficiency ratings."""
    from rich.table import Table
    from cost_intel.optimize import get_waste_index

    waste_runs = get_waste_runs()
    wi = get_waste_index()

    # Summary
    console.print(f"Waste Index: [bold]{wi['waste_index']:.1%}[/bold] "
                  f"(${wi['waste_spend']:.4f} of ${wi['total_spend']:.4f})")

    if not waste_runs:
        console.print("[green]No waste detected — all runs rated A/B/C.[/green]")
        return

    table = Table(title="Waste Runs (Rating D or F)")
    table.add_column("Run ID", style="cyan", max_width=12)
    table.add_column("Label", max_width=20)
    table.add_column("Model", max_width=25)
    table.add_column("Cost", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("CPQP", justify="right")
    table.add_column("Rating", justify="right")
    for r in waste_runs:
        rating = r.get("rating", "N/A")
        table.add_row(
            r["run_id"][:8],
            r["label"] or "",
            r["model_id"] or "",
            f"${r['total_cost']:.4f}",
            f"{r['combined_score']:.2f}" if r["combined_score"] is not None else "N/A",
            f"${r['cpqp']:.4f}" if r["cpqp"] is not None else "N/A",
            f"[bold red]{rating}[/bold red]" if rating == "F" else f"[red]{rating}[/red]",
        )
    console.print(table)
```

### Step 5: Run test to verify pass

```bash
pytest tests/test_cli_cpqp.py -v
```
Expected: 4 passed

### Step 6: Commit

```bash
git add src/cost_intel/cli.py tests/test_cli_cpqp.py
git commit -m "feat: cpqp + waste CLI — percentile ratings, --last flag, rating column display"
```

---

## Task 2.3: Model Comparison — `cost-intel compare-models` with Efficiency Delta

**Objective:** Implement `compare_models` with CPQP join and Model Efficiency Delta metric.

**Files:**
- Create: `src/cost_intel/compare.py`
- Modify: `src/cost_intel/cli.py`
- Test: `tests/test_compare.py`

### Step 1: Write failing test

```python
# tests/test_compare.py
import pytest
from cost_intel.compare import compare_models

def test_compare_models_basic(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    upsert_pricing("anthropic/claude-sonnet-4", "anthropic", 3.0, 15.0)
    record_run("openai/gpt-4o", 1000, 500, label="summarize")
    record_run("anthropic/claude-sonnet-4", 800, 400, label="summarize")
    results = compare_models(label="summarize")
    assert len(results) == 2
    gpt = next(r for r in results if r["model_id"] == "openai/gpt-4o")
    claude = next(r for r in results if r["model_id"] == "anthropic/claude-sonnet-4")
    assert gpt["total_cost"] == 7.5
    assert claude["total_cost"] == 8.4

def test_compare_models_includes_cpqp_delta(tmp_cost_intel_home):
    """compare_models must report avg_cpqp and delta_cpqp."""
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    from cost_intel.quality import import_score
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    upsert_pricing("openai/gpt-4o-mini", "openai", 0.15, 0.6)
    rid1 = record_run("openai/gpt-4o", 1000, 500, label="summarize")
    import_score(rid1, score=0.8, source="test")
    rid2 = record_run("openai/gpt-4o-mini", 1000, 500, label="summarize")
    import_score(rid2, score=0.7, source="test")
    results = compare_models(label="summarize")
    # Both models should have avg_cpqp
    for r in results:
        assert "avg_cpqp" in r
    # delta_cpqp should be present (relative to cheapest baseline)
    deltas = [r.get("delta_cpqp") for r in results]
    assert any(d is not None for d in deltas)
```

### Step 2: Run test to verify failure

```bash
pytest tests/test_compare.py -v
```
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Write `compare.py`

```python
# src/cost_intel/compare.py
"""Model comparison — cost efficiency and CPQP delta across models."""

from typing import Optional

from cost_intel.db import get_connection


def compare_models(
    label: Optional[str] = None,
    models: Optional[list[str]] = None,
) -> list[dict]:
    """Compare cost and CPQP across models for the same task.

    Returns a list of dicts with per-model aggregates including:
    - model_id, total_runs, total_cost, avg_cost_per_run
    - total_input_tokens, total_output_tokens
    - avg_cpqp (average CPQP for runs with quality scores)
    - delta_cpqp (difference from the most efficient model)
    """
    conn = get_connection()
    query = """
        SELECT
            cr.model_id,
            cr.label,
            COUNT(DISTINCT cr.run_id) AS total_runs,
            COALESCE(SUM(crc.call_cost), 0) AS total_cost,
            COALESCE(AVG(crc.call_cost), 0) AS avg_cost_per_run,
            COALESCE(SUM(crc.input_tokens), 0) AS total_input_tokens,
            COALESCE(SUM(crc.output_tokens), 0) AS total_output_tokens,
            AVG(crp.cpqp) AS avg_cpqp
        FROM cost_runs cr
        JOIN cost_run_calls crc ON cr.run_id = crc.run_id
        LEFT JOIN cost_run_cpqp crp ON cr.run_id = crp.run_id
    """
    params: list = []
    if label:
        query += " WHERE cr.label = ?"
        params.append(label)
    if models:
        placeholders = ",".join("?" for _ in models)
        query += f" AND cr.model_id IN ({placeholders})"
        params.extend(models)
    query += " GROUP BY cr.model_id ORDER BY avg_cost_per_run ASC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = [dict(r) for r in rows]

    # Compute delta_cpqp relative to the most efficient model
    # (lowest avg_cpqp among models that have quality data)
    cpqp_values = [r["avg_cpqp"] for r in results if r.get("avg_cpqp") is not None]
    if cpqp_values:
        baseline = min(cpqp_values)
        for r in results:
            if r.get("avg_cpqp") is not None:
                r["delta_cpqp"] = round(r["avg_cpqp"] - baseline, 4)
            else:
                r["delta_cpqp"] = None

    return results
```

### Step 4: Update cli.py — `compare-models` command

```python
from cost_intel.compare import compare_models

@app.command(name="compare-models")
def compare_cmd(
    label: str = typer.Option(None, "--label", "-l", help="Filter by task label"),
    models: str = typer.Option(None, "--models", "-m",
        help="Comma-separated model IDs to compare"),
):
    """Compare cost efficiency and CPQP across models."""
    from rich.table import Table
    model_list = [m.strip() for m in models.split(",")] if models else None
    results = compare_models(label=label, models=model_list)
    table = Table(title="Model Comparison")
    table.add_column("Model", style="cyan")
    table.add_column("Runs", justify="right")
    table.add_column("Total Cost", justify="right")
    table.add_column("Avg Cost/Run", justify="right")
    table.add_column("Avg CPQP", justify="right")
    table.add_column("Δ CPQP", justify="right")
    for r in results:
        delta = r.get("delta_cpqp")
        delta_str = f"{delta:+.4f}" if delta is not None else "N/A"
        table.add_row(
            r["model_id"],
            str(r["total_runs"]),
            f"${r['total_cost']:.4f}",
            f"${r['avg_cost_per_run']:.4f}",
            f"{r['avg_cpqp']:.4f}" if r.get("avg_cpqp") is not None else "N/A",
            delta_str,
        )
    console.print(table)
```

### Step 5: Run test to verify pass

```bash
pytest tests/test_compare.py -v
```
Expected: 2 passed

### Step 6: Commit

```bash
git add src/cost_intel/compare.py src/cost_intel/cli.py tests/test_compare.py
git commit -m "feat: model comparison with CPQP delta — cost-intel compare-models"
```

---

## Task 2.4: Optimization — `cost-intel optimize` with `--target-cpqp` + waste index fix

**Objective:** Implement `cost-intel optimize` with fixed parameter naming (no shadowing), working `--target-cpqp` behavior, and corrected `get_waste_index()` SQL.

**Files:**
- Create: `src/cost_intel/optimize.py`
- Modify: `src/cost_intel/cli.py`
- Test: `tests/test_optimize.py`

### Step 1: Write failing test

```python
# tests/test_optimize.py
import pytest
from cost_intel.optimize import suggest_model_routing, get_waste_index

def test_suggest_model_routing(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    upsert_pricing("openai/gpt-4o-mini", "openai", 0.15, 0.6)
    for _ in range(10):
        record_run("openai/gpt-4o", 1000, 500, label="summarize")
    for _ in range(10):
        record_run("openai/gpt-4o-mini", 1000, 500, label="summarize")
    suggestions = suggest_model_routing(label="summarize")
    assert len(suggestions) > 0
    mini = next((s for s in suggestions if s["model_id"] == "openai/gpt-4o-mini"), None)
    assert mini is not None
    assert mini["avg_cost_per_run"] < 1.0

def test_get_waste_index_valid_sql(tmp_cost_intel_home):
    """get_waste_index must not crash (no SUM-in-WHERE bug)."""
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    from cost_intel.quality import import_score
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    for i in range(9):
        rid = record_run("openai/gpt-4o", 10, 5, label=f"good-{i}")
        import_score(rid, score=0.95, source="test")
    expensive = record_run("openai/gpt-4o", 10000, 5000, label="waste")
    import_score(expensive, score=0.05, source="test")
    wi = get_waste_index()
    assert "total_spend" in wi
    assert "waste_spend" in wi
    assert "waste_index" in wi
    assert 0 <= wi["waste_index"] <= 1

def test_optimize_cli_no_shadow_crash(tmp_cost_intel_home):
    """--suggest-model-routing must not crash with TypeError."""
    from typer.testing import CliRunner
    from cost_intel.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["optimize", "--suggest-model-routing"])
    # Must NOT contain "TypeError" or "not callable"
    assert "TypeError" not in result.output
    assert "not callable" not in result.output

def test_optimize_target_cpqp(tmp_cost_intel_home):
    """--target-cpqp must show runs exceeding the target."""
    from typer.testing import CliRunner
    from cost_intel.cli import app
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    from cost_intel.quality import import_score
    runner = CliRunner()
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    rid = record_run("openai/gpt-4o", 1000, 500, label="test")
    import_score(rid, score=0.1, source="test")  # Low quality → high CPQP
    result = runner.invoke(app, ["optimize", "--target-cpqp", "1.0"])
    assert result.exit_code == 0
    # Should show the run as exceeding target
    assert "test" in result.output or rid[:8] in result.output
```

### Step 2: Run test to verify failure

```bash
pytest tests/test_optimize.py -v
```
Expected: FAIL — `ModuleNotFoundError`

### Step 3: Write `optimize.py`

```python
# src/cost_intel/optimize.py
"""Optimization suggestions — model routing, waste index, target CPQP."""

from typing import Optional

from cost_intel.db import get_connection


def suggest_model_routing(label: Optional[str] = None) -> list[dict]:
    """Suggest cheaper models for the same task based on historical data.

    Only suggests models with at least 3 runs for statistical relevance.
    """
    conn = get_connection()
    query = """
        SELECT
            cr.model_id,
            cr.label,
            COUNT(*) AS total_runs,
            AVG(crc.call_cost) AS avg_cost_per_run,
            MIN(crc.call_cost) AS min_cost,
            MAX(crc.call_cost) AS max_cost
        FROM cost_runs cr
        JOIN cost_run_calls crc ON cr.run_id = crc.run_id
    """
    params: list = []
    if label:
        query += " WHERE cr.label = ?"
        params.append(label)
    query += " GROUP BY cr.model_id HAVING total_runs >= 3 ORDER BY avg_cost_per_run ASC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_waste_index() -> dict:
    """Calculate waste index: % of spend on D/F-rated runs.

    Uses the percentile-based rating from the cost_run_cpqp view.
    SQL is written with a CTE to avoid aggregates in WHERE clause.
    """
    conn = get_connection()
    total_row = conn.execute(
        "SELECT COALESCE(SUM(call_cost), 0) AS total FROM cost_run_calls"
    ).fetchone()
    total = total_row["total"] if total_row else 0

    # Use the CPQP view's rating column (percentile-based D/F)
    waste_row = conn.execute(
        """
        SELECT COALESCE(SUM(total_cost), 0) AS waste_total
        FROM cost_run_cpqp
        WHERE rating IN ('D', 'F')
        """
    ).fetchone()
    conn.close()

    waste = waste_row["waste_total"] if waste_row else 0
    return {
        "total_spend": total,
        "waste_spend": waste,
        "waste_index": round(waste / total, 4) if total > 0 else 0.0,
    }


def get_runs_above_target_cpqp(target: float) -> list[dict]:
    """Return all runs whose CPQP exceeds the given target."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM cost_run_cpqp
        WHERE combined_score IS NOT NULL
        AND cpqp > ?
        ORDER BY cpqp DESC
        """,
        (target,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

### Step 4: Update cli.py — `optimize` command (fixed parameter naming)

```python
from cost_intel.optimize import suggest_model_routing, get_waste_index, get_runs_above_target_cpqp

@app.command()
def optimize(
    target_cpqp: float = typer.Option(None, "--target-cpqp",
        help="Show runs exceeding this CPQP target"),
    route: bool = typer.Option(False, "--suggest-model-routing",
        help="Suggest cheaper models for the same task"),
):
    """Find optimization opportunities."""
    from rich.table import Table

    if target_cpqp is not None:
        results = get_runs_above_target_cpqp(target_cpqp)
        table = Table(title=f"Runs Above Target CPQP (${target_cpqp:.4f})")
        table.add_column("Run ID", style="cyan", max_width=12)
        table.add_column("Label", max_width=20)
        table.add_column("Model", max_width=25)
        table.add_column("Cost", justify="right")
        table.add_column("Score", justify="right")
        table.add_column("CPQP", justify="right")
        table.add_column("Rating", justify="right")
        for r in results:
            table.add_row(
                r["run_id"][:8], r["label"] or "", r["model_id"] or "",
                f"${r['total_cost']:.4f}",
                f"{r['combined_score']:.2f}" if r["combined_score"] is not None else "N/A",
                f"${r['cpqp']:.4f}" if r["cpqp"] is not None else "N/A",
                r.get("rating", "N/A"),
            )
        console.print(table)
        console.print(f"[dim]{len(results)} run(s) exceed target CPQP[/dim]")
    elif route:
        results = suggest_model_routing()
        table = Table(title="Model Routing Suggestions")
        table.add_column("Model", style="cyan")
        table.add_column("Runs", justify="right")
        table.add_column("Avg Cost/Run", justify="right")
        table.add_column("Min", justify="right")
        table.add_column("Max", justify="right")
        for r in results:
            table.add_row(
                r["model_id"], str(r["total_runs"]),
                f"${r['avg_cost_per_run']:.4f}",
                f"${r['min_cost']:.4f}", f"${r['max_cost']:.4f}",
            )
        console.print(table)
    else:
        wi = get_waste_index()
        table = Table(title="Waste Index")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_row("Waste Index", f"{wi['waste_index']:.1%}")
        table.add_row("Total Spend", f"${wi['total_spend']:.4f}")
        table.add_row("Waste Spend", f"${wi['waste_spend']:.4f}")
        console.print(table)
```

### Step 5: Run test to verify pass

```bash
pytest tests/test_optimize.py -v
```
Expected: 4 passed

### Step 6: Commit

```bash
git add src/cost_intel/optimize.py src/cost_intel/cli.py tests/test_optimize.py
git commit -m "feat: optimize CLI — fixed shadow bug, --target-cpqp, CTE-based waste index"
```

---

## Task 2.5: CPQP Trend — `get_cpqp_trend()` + `cost-intel trends --metric cpqp`

**Objective:** Add week-over-week CPQP trend analysis and expose it via the trends command.

**Files:**
- Modify: `src/cost_intel/trends.py`
- Modify: `src/cost_intel/cli.py`
- Test: `tests/test_trends.py` (add new tests)

### Step 1: Write failing test

```python
# Add to tests/test_trends.py
from cost_intel.trends import get_cpqp_trend

def test_get_cpqp_trend(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    from cost_intel.quality import import_score
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    # Create runs with quality scores
    for i in range(5):
        rid = record_run("openai/gpt-4o", 100, 50, label=f"run-{i}")
        import_score(rid, score=0.8, source="test")
    trend = get_cpqp_trend()
    assert "this_window" in trend
    assert "prior_window" in trend
    assert "ratio" in trend
    assert isinstance(trend["ratio"], float)

def test_trends_cli_metric_cpqp(tmp_cost_intel_home):
    """cost-intel trends --metric cpqp must work."""
    from typer.testing import CliRunner
    from cost_intel.cli import app
    runner = CliRunner()
    result = runner.invoke(app, ["trends", "--metric", "cpqp"])
    assert result.exit_code == 0
```

### Step 2: Run test to verify failure

```bash
pytest tests/test_trends.py::test_get_cpqp_trend tests/test_trends.py::test_trends_cli_metric_cpqp -v
```
Expected: FAIL — `get_cpqp_trend` not defined

### Step 3: Add `get_cpqp_trend()` to `trends.py`

Add to `src/cost_intel/trends.py`:

```python
def get_cpqp_trend(window_days: int = 7) -> dict:
    """Compute week-over-week CPQP trend.

    Returns:
        dict with keys:
        - this_window: average CPQP in the last window_days
        - prior_window: average CPQP in the window before that
        - ratio: this_window / prior_window (lower = improving)
    """
    conn = get_connection()
    this_row = conn.execute(
        """
        SELECT AVG(cpqp) AS avg_cpqp
        FROM cost_run_cpqp
        WHERE combined_score IS NOT NULL
        AND started_at >= datetime('now', ?)
        """,
        (f"-{window_days} days",),
    ).fetchone()

    prior_row = conn.execute(
        """
        SELECT AVG(cpqp) AS avg_cpqp
        FROM cost_run_cpqp
        WHERE combined_score IS NOT NULL
        AND started_at >= datetime('now', ?)
        AND started_at < datetime('now', ?)
        """,
        (f"-{window_days * 2} days", f"-{window_days} days"),
    ).fetchone()
    conn.close()

    this_avg = this_row["avg_cpqp"] if this_row and this_row["avg_cpqp"] else 0
    prior_avg = prior_row["avg_cpqp"] if prior_row and prior_row["avg_cpqp"] else 0
    ratio = round(this_avg / prior_avg, 4) if prior_avg > 0 else 0.0

    return {
        "this_window": round(this_avg, 4),
        "prior_window": round(prior_avg, 4),
        "ratio": ratio,
    }
```

### Step 4: Update cli.py — `trends` command with `--metric` option

Modify the existing `trends` command in `src/cost_intel/cli.py`:

```python
from cost_intel.trends import get_trends, get_cpqp_trend

@app.command()
def trends(
    days: int = typer.Option(30, "--days", "-d", help="Number of days"),
    metric: str = typer.Option("spending", "--metric", "-m",
        help="Metric: spending (default) or cpqp"),
):
    """Show spending or CPQP trends."""
    from rich.table import Table

    if metric == "cpqp":
        trend = get_cpqp_trend(window_days=days)
        table = Table(title=f"CPQP Trend (last {days} days)")
        table.add_column("Window", style="cyan")
        table.add_column("Avg CPQP", justify="right")
        table.add_row("This window", f"${trend['this_window']:.4f}")
        table.add_row("Prior window", f"${trend['prior_window']:.4f}")
        ratio = trend["ratio"]
        ratio_str = f"{ratio:.2f}"
        if ratio > 1:
            ratio_str = f"[red]↑ {ratio_str}[/red] (degrading)"
        elif ratio > 0:
            ratio_str = f"[green]↓ {ratio_str}[/green] (improving)"
        table.add_row("Ratio", ratio_str)
        console.print(table)
    else:
        data = get_trends(days)
        table = Table(title=f"Spending Trends (last {days} days)")
        table.add_column("Day", style="cyan")
        table.add_column("Runs", justify="right")
        table.add_column("Total Cost", justify="right")
        table.add_column("Input Tokens", justify="right")
        table.add_column("Output Tokens", justify="right")
        for r in data:
            table.add_row(
                r["day"], str(r["total_runs"]),
                f"${r['total_cost']:.4f}",
                str(r["total_input_tokens"]), str(r["total_output_tokens"]),
            )
        console.print(table)
```

### Step 5: Run test to verify pass

```bash
pytest tests/test_trends.py::test_get_cpqp_trend tests/test_trends.py::test_trends_cli_metric_cpqp -v
```
Expected: 2 passed

### Step 6: Commit

```bash
git add src/cost_intel/trends.py src/cost_intel/cli.py tests/test_trends.py
git commit -m "feat: week-over-week CPQP trend — get_cpqp_trend() + trends --metric cpqp"
```

---

## Phase 2 Summary

### Tasks

| Task | Description | Key Deliverable |
|------|-------------|-----------------|
| **2.0** | Schema migration framework + `002_add_quality.sql` | `quality_scores` table, `cost_run_cpqp` view with percentile ratings |
| **2.1** | Quality score import + adapters | `quality.py`, `eval_harness.py`, `braintrust.py`, `import-scores` CLI |
| **2.2** | CPQP report + waste CLI | `cpqp` and `waste` commands with rating column, `--last` flag |
| **2.3** | Model comparison with Efficiency Delta | `compare-models` with `avg_cpqp` + `delta_cpqp` |
| **2.4** | Optimization with fixed bugs | `optimize` CLI (no shadow crash, `--target-cpqp` works, CTE waste index) |
| **2.5** | CPQP trend analysis | `get_cpqp_trend()`, `trends --metric cpqp` |

### Audit Fixes Applied

| Finding | Severity | Fix Location |
|---------|----------|-------------|
| No schema migration strategy | CRITICAL | Task 2.0 — migration runner + numbered SQL files |
| CPQP percentile ratings missing | CRITICAL | Task 2.0 — `cost_run_cpqp` view with `PERCENT_RANK()` |
| `get_waste_index()` SQL invalid | CRITICAL | Task 2.4 — rewritten using view's `rating IN ('D','F')` |
| `optimize` CLI bool flag shadows function | CRITICAL | Task 2.4 — parameter renamed to `route: bool` |
| Eval Harness adapter stub | HIGH | Task 2.1 — full `eval_harness.py` implementation |
| Braintrust adapter stub | HIGH | Task 2.1 — full `braintrust.py` implementation |
| CSV lacks `--mapping` | HIGH | Task 2.1 — `mapping` param in `import_scores_csv()` |
| `combined_score` not computed | HIGH | Task 2.1 — `compute_combined_score()` helper |
| `--target-cpqp` has no behavior | HIGH | Task 2.4 — `get_runs_above_target_cpqp()` |
| `--last`/`--days` missing on cpqp | HIGH | Task 2.2 — `_parse_window()` + `--last` flag |
| `Optional` not imported | MEDIUM | All modules include `from typing import Optional` |
| No CPQP trend | MEDIUM | Task 2.5 — `get_cpqp_trend()` |
| No Model Efficiency Delta | MEDIUM | Task 2.3 — `avg_cpqp` + `delta_cpqp` in `compare_models` |

### Validation (Research §9 Phase 2)

> **Deliverable:** CPQP metric + waste detection
> **Validation:** Import Eval Harness scores, verify CPQP matches manual calculation

```bash
# After completing all Phase 2 tasks:
pip install -e ".[dev]"
pytest tests/ -v  # All Phase 1 + Phase 2 tests must pass

# Manual validation:
cost-intel import-scores --source eval-harness --db-path ~/.eval-harness/eval.db
cost-intel cpqp --last 30d
cost-intel waste
cost-intel compare-models --label "summarization"
cost-intel optimize --target-cpqp 0.05
cost-intel trends --metric cpqp --days 14
```
# Cost Intelligence Plan — Phase 3 & Phase 4 (Revised)

> **Audit-driven rewrite.** This file replaces the Phase 3 and Phase 4 sections of `plan.md`.
> All CRITICAL, HIGH, and MEDIUM findings from `droid-audit.md` affecting these phases are addressed.
> Another process will assemble the full plan from the Phase 1/2 rewrite and this file.

---

## Phase 3: CI/CD + Alerts (Weeks 7-9)

> **Deliverable:** CI/CD cost gates + budget alerts (Slack webhook, email).

### Task 3.0: Shared Utilities — `_parse_window()` Helper

**Objective:** Create the reusable duration-parser used by `gate`, `report`, `trends`, `cpqp`, and `export` commands. This fixes the audit finding that `--window 7d` is rejected because the CLI declares `window: int`.

**Files:**
- Create: `src/cost_intel/duration.py`
- Test: `tests/test_duration.py`

**Step 1: Write failing test**

```python
# tests/test_duration.py
import pytest
from cost_intel.duration import parse_window

def test_parse_window_days():
    assert parse_window("7d") == 7
    assert parse_window("30d") == 30
    assert parse_window("1d") == 1

def test_parse_window_hours():
    assert parse_window("24h") == 1
    assert parse_window("48h") == 2
    assert parse_window("12h") == 1  # floor(12/24) -> max(1, 0) -> 1

def test_parse_window_plain_int():
    assert parse_window("7") == 7
    assert parse_window("30") == 30

def test_parse_window_whitespace():
    assert parse_window("  7d  ") == 7

def test_parse_window_case_insensitive():
    assert parse_window("7D") == 7
    assert parse_window("24H") == 1

def test_parse_window_invalid():
    with pytest.raises(ValueError):
        parse_window("abc")
    with pytest.raises(ValueError):
        parse_window("")
```

**Step 2: Run test to verify failure**

```bash
pytest tests/test_duration.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/cost_intel/duration.py
"""Duration string parser for CLI window arguments."""


def parse_window(value: str) -> int:
    """Parse a duration string into days (int).

    Accepts:
        - "7d"  -> 7
        - "24h" -> 1
        - "30"  -> 30 (plain integer = days)

    Hours are converted to days with a minimum of 1.
    Whitespace is stripped; case is insensitive.
    """
    value = value.strip().lower()
    if value.endswith("d"):
        return int(value[:-1])
    if value.endswith("h"):
        return max(1, int(value[:-1]) // 24)
    return int(value)
```

**Step 4: Run test to verify pass**

```bash
pytest tests/test_duration.py -v
```
Expected: 6 passed

**Step 5: Commit**

```bash
git add src/cost_intel/duration.py tests/test_duration.py
git commit -m "feat: shared duration parser — parse_window()"
```

---

### Task 3.1: Cost Gate — `cost-intel gate`

**Objective:** Implement `cost-intel gate` for CI/CD integration with correct `--window` parsing, `--max-waste-index` enforcement, no-quality-data guard, and `--format json` output.

**Audit fixes applied:**
- `--window` accepts string via `parse_window()` (was `int`, rejected `7d`)
- `--max-waste-index` actually calls `get_waste_index()` (was silently ignored)
- Gate with no quality data returns informative failure instead of passing silently
- `--format json` produces machine-readable output for CI

**Files:**
- Create: `src/cost_intel/gate.py`
- Modify: `src/cost_intel/cli.py`
- Test: `tests/test_gate.py`

**Step 1: Write failing test**

```python
# tests/test_gate.py
import json
import pytest
from cost_intel.gate import check_gate

def test_gate_passes_when_under_threshold(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    from cost_intel.quality import import_score
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50)
    import_score(run_id, score=0.9, source="test")
    passed, msg = check_gate(max_avg_cpqp=10.0, window_days=7)
    assert passed is True

def test_gate_fails_when_over_threshold(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    from cost_intel.quality import import_score
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 10000, 5000)
    import_score(run_id, score=0.01, source="test")
    passed, msg = check_gate(max_avg_cpqp=0.10, window_days=7)
    assert passed is False
    assert "CPQP" in msg

def test_gate_no_quality_data_returns_fail(tmp_cost_intel_home):
    """When max_avg_cpqp is set but no runs have quality scores, gate must fail
    with an informative message — not silently pass."""
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    record_run("openai/gpt-4o", 100, 50)
    # No quality scores imported
    passed, msg = check_gate(max_avg_cpqp=10.0, window_days=7)
    assert passed is False
    assert "No quality score data" in msg

def test_gate_waste_index_passes(tmp_cost_intel_home):
    from cost_intel.db import init_db
    init_db()
    # No runs → waste index = 0 → passes
    passed, msg = check_gate(max_waste_index=0.20, window_days=7)
    assert passed is True

def test_gate_waste_index_fails(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    from cost_intel.quality import import_score
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    # Create a high-cost, low-quality run (CPQP = 7.5 / 0.01 = 750.0)
    run_id = record_run("openai/gpt-4o", 1000, 500)
    import_score(run_id, score=0.01, source="test")
    passed, msg = check_gate(max_waste_index=0.20, window_days=7)
    assert passed is False
    assert "Waste index" in msg

def test_gate_budget_check(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.trends import set_budget
    init_db()
    set_budget(monthly=100, alert_threshold=80)
    passed, msg = check_gate(budget_check=True)
    assert passed is True  # No spending yet

def test_gate_budget_alert_triggered(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.trends import set_budget
    init_db()
    set_budget(monthly=100, alert_threshold=0)  # 0% threshold → always triggered
    passed, msg = check_gate(budget_check=True)
    assert passed is False
    assert "Budget" in msg
```

**Step 2: Run test to verify failure**

```bash
pytest tests/test_gate.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/cost_intel/gate.py
"""CI/CD cost gates — fail builds when cost thresholds are exceeded."""

from typing import Optional

from cost_intel.db import get_connection
from cost_intel.optimize import get_waste_index


def check_gate(
    max_avg_cpqp: Optional[float] = None,
    max_waste_index: Optional[float] = None,
    budget_check: bool = False,
    window_days: int = 7,
) -> tuple[bool, str]:
    """Check cost gates. Returns (passed, message).

    If max_avg_cpqp is set but zero runs have quality scores in the window,
    returns (False, "No quality score data in window — cannot evaluate CPQP gate").
    """
    with get_connection() as conn:
        if max_avg_cpqp is not None:
            row = conn.execute(
                """
                SELECT COUNT(*) AS scored_runs, AVG(cpqp) AS avg_cpqp
                FROM cost_run_cpqp
                WHERE combined_score IS NOT NULL
                AND started_at >= datetime('now', ?)
                """,
                (f"-{window_days} days",),
            ).fetchone()

            scored_runs = row["scored_runs"] if row else 0
            avg_cpqp = row["avg_cpqp"] if row and row["avg_cpqp"] else None

            if scored_runs == 0:
                return (
                    False,
                    "No quality score data in window — cannot evaluate CPQP gate",
                )

            if avg_cpqp > max_avg_cpqp:
                return (
                    False,
                    f"Average CPQP ${avg_cpqp:.4f} exceeds threshold "
                    f"${max_avg_cpqp:.4f}",
                )

        if max_waste_index is not None:
            wi = get_waste_index()
            if wi["waste_index"] > max_waste_index:
                return (
                    False,
                    f"Waste index {wi['waste_index']:.1%} exceeds threshold "
                    f"{max_waste_index:.1%}",
                )

        if budget_check:
            from cost_intel.trends import get_budget_status

            status = get_budget_status()
            if status["budget_set"] and status["alert_triggered"]:
                return (
                    False,
                    f"Budget {status['percent_used']}% used "
                    f"(threshold {status['alert_threshold']}%)",
                )

    return True, "All gates passed"
```

**Step 4: Update cli.py**

```python
from cost_intel.gate import check_gate
from cost_intel.duration import parse_window

@app.command()
def gate(
    max_avg_cpqp: Optional[float] = typer.Option(
        None, "--max-avg-cpqp", help="Max average CPQP threshold"
    ),
    max_waste_index: Optional[float] = typer.Option(
        None, "--max-waste-index", help="Max waste index threshold (0.0-1.0)"
    ),
    budget_check: bool = typer.Option(
        False, "--budget-check", help="Check budget threshold"
    ),
    window: str = typer.Option(
        "7d", "--window", "-w", help="Window (e.g. 7d, 30d, 24h, 7)"
    ),
    format: str = typer.Option(
        "text", "--format", "-f", help="Output format: text or json"
    ),
):
    """CI/CD cost gate. Exits 0 if passed, 1 if failed."""
    import json as json_mod

    window_days = parse_window(window)
    passed, msg = check_gate(
        max_avg_cpqp=max_avg_cpqp,
        max_waste_index=max_waste_index,
        budget_check=budget_check,
        window_days=window_days,
    )
    if format == "json":
        console.print(json_mod.dumps({"passed": passed, "message": msg}))
    else:
        if passed:
            console.print(f"[green]✓[/green] {msg}")
        else:
            console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(code=0 if passed else 1)
```

**Step 5: Run test to verify pass**

```bash
pytest tests/test_gate.py -v
```
Expected: 7 passed

**Step 6: Commit**

```bash
git add src/cost_intel/gate.py src/cost_intel/cli.py tests/test_gate.py
git commit -m "feat: CI/CD cost gate — cost-intel gate (with waste-index, no-quality guard, json format)"
```

---

### Task 3.2: GitHub Actions Integration Example

**Objective:** Create a GitHub Actions workflow example for cost gating. Fix the `--window` usage to use the string format.

**Files:**
- Create: `examples/github-actions-cost-gate.yml`

```yaml
# examples/github-actions-cost-gate.yml
name: Cost Gate

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  cost-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install cost-intel
      - name: Check cost gate (CPQP)
        run: cost-intel gate --max-avg-cpqp 0.10 --window 7d
      - name: Check cost gate (waste index)
        run: cost-intel gate --max-waste-index 0.20 --window 7d
      - name: Check cost gate (budget)
        run: cost-intel gate --budget-check
      - name: Check cost gate (JSON output)
        run: cost-intel gate --max-avg-cpqp 0.10 --window 7d --format json
```

**Step 1: Commit**

```bash
git add examples/github-actions-cost-gate.yml
git commit -m "feat: GitHub Actions cost gate example (fixed --window usage)"
```

---

### Task 3.3: Budget Alerts — Slack Webhook + Email

**Objective:** Implement budget alert dispatch via Slack webhook and SMTP email. This is a new task required by research §9 Phase 3 deliverable 2 ("Budget alerts (Slack webhook, email)") which was entirely missing from the original plan.

**Audit fixes applied:**
- Config keys for `slack_webhook_url`, `smtp_host`, `smtp_from`, `alert_recipients`
- `cost-intel alert test` CLI command
- Alert dispatcher hooked into budget checks
- `cost-intel check-budget` cron entrypoint

**Files:**
- Create: `src/cost_intel/alerts.py`
- Modify: `src/cost_intel/cli.py`
- Modify: `src/cost_intel/config.py` (add alert config keys)
- Test: `tests/test_alerts.py`

**Step 1: Write failing test**

```python
# tests/test_alerts.py
import json
import pytest
from unittest.mock import patch, MagicMock
from cost_intel.alerts import send_slack_alert, send_email_alert, check_and_alert

def test_send_slack_alert_success():
    with patch("cost_intel.alerts.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        result = send_slack_alert(
            webhook_url="https://hooks.slack.com/test",
            message="Budget alert: 85% used",
        )
        assert result is True
        mock_post.assert_called_once()

def test_send_slack_alert_skips_without_url():
    result = send_slack_alert(webhook_url="", message="test")
    assert result is False

def test_send_email_alert_success():
    with patch("cost_intel.alerts.smtplib.SMTP") as mock_smtp:
        mock_smtp.return_value.__enter__ = MagicMock()
        mock_smtp.return_value.__exit__ = MagicMock()
        result = send_email_alert(
            smtp_host="smtp.example.com",
            smtp_from="alerts@example.com",
            recipients=["team@example.com"],
            subject="Budget Alert",
            body="Budget 85% used",
        )
        assert result is True

def test_send_email_alert_skips_without_host():
    result = send_email_alert(
        smtp_host="", smtp_from="a@b.com", recipients=["c@d.com"],
        subject="test", body="test",
    )
    assert result is False

def test_check_and_alert_triggers(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.trends import set_budget
    init_db()
    set_budget(monthly=100, alert_threshold=0)  # 0% → always triggered
    with patch("cost_intel.alerts.send_slack_alert", return_value=True) as mock_slack:
        with patch("cost_intel.alerts.get_config") as mock_cfg:
            mock_cfg.return_value = {
                "slack_webhook_url": "https://hooks.slack.com/test",
                "smtp_host": "",
                "smtp_from": "",
                "alert_recipients": [],
            }
            result = check_and_alert()
            assert result["alert_sent"] is True
            assert result["triggered"] is True

def test_check_and_alert_no_trigger(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.trends import set_budget
    init_db()
    set_budget(monthly=1000, alert_threshold=99)
    result = check_and_alert()
    assert result["triggered"] is False
    assert result["alert_sent"] is False
```

**Step 2: Run test to verify failure**

```bash
pytest tests/test_alerts.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/cost_intel/alerts.py
"""Budget alert dispatch — Slack webhook + SMTP email."""

from typing import Optional

from cost_intel.config import get_config
from cost_intel.trends import get_budget_status


def send_slack_alert(webhook_url: str, message: str) -> bool:
    """Send alert to Slack via incoming webhook. Returns True on success."""
    if not webhook_url:
        return False
    try:
        import httpx

        resp = httpx.post(
            webhook_url,
            json={"text": message},
            timeout=10.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


def send_email_alert(
    smtp_host: str,
    smtp_from: str,
    recipients: list[str],
    subject: str,
    body: str,
) -> bool:
    """Send alert via SMTP. Returns True on success."""
    if not smtp_host or not recipients:
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = ", ".join(recipients)

        with smtplib.SMTP(smtp_host) as server:
            server.sendmail(smtp_from, recipients, msg.as_string())
        return True
    except Exception:
        return False


def check_and_alert() -> dict:
    """Check budget status and send alerts if triggered.

    Returns {"triggered": bool, "alert_sent": bool, "message": str}.
    """
    status = get_budget_status()
    result = {
        "triggered": False,
        "alert_sent": False,
        "message": "",
    }

    if not status["budget_set"]:
        return result

    if not status["alert_triggered"]:
        return result

    result["triggered"] = True
    message = (
        f"⚠️ Cost Intelligence Budget Alert\n"
        f"Budget: ${status['monthly_budget']:.2f}/month\n"
        f"Spent: ${status['spent_this_month']:.2f} "
        f"({status['percent_used']}%)\n"
        f"Threshold: {status['alert_threshold']}%"
    )
    result["message"] = message

    cfg = get_config()
    sent = False

    slack_url = cfg.get("slack_webhook_url", "")
    if slack_url:
        sent = send_slack_alert(slack_url, message) or sent

    smtp_host = cfg.get("smtp_host", "")
    smtp_from = cfg.get("smtp_from", "")
    recipients = cfg.get("alert_recipients", [])
    if smtp_host and recipients:
        sent = (
            send_email_alert(
                smtp_host=smtp_host,
                smtp_from=smtp_from,
                recipients=recipients,
                subject="Cost Intelligence Budget Alert",
                body=message,
            )
            or sent
        )

    result["alert_sent"] = sent
    return result
```

**Step 4: Update cli.py — add `alert` and `check-budget` commands**

```python
from cost_intel.alerts import check_and_alert, send_slack_alert, send_email_alert

@app.command(name="alert")
def alert_cmd(
    action: str = typer.Argument(..., help="Action: test, check"),
):
    """Manage budget alerts."""
    if action == "test":
        cfg = get_config()
        console.print("[bold]Alert configuration:[/bold]")
        console.print(f"  Slack webhook: {'set' if cfg.get('slack_webhook_url') else 'not set'}")
        console.print(f"  SMTP host: {cfg.get('smtp_host', 'not set')}")
        console.print(f"  Recipients: {cfg.get('alert_recipients', [])}")
        # Send test message
        slack_url = cfg.get("slack_webhook_url", "")
        if slack_url:
            ok = send_slack_alert(slack_url, "Cost Intelligence: test alert")
            console.print(f"  Slack test: {'[green]sent[/green]' if ok else '[red]failed[/red]'}")
        smtp_host = cfg.get("smtp_host", "")
        recipients = cfg.get("alert_recipients", [])
        if smtp_host and recipients:
            ok = send_email_alert(
                smtp_host=smtp_host,
                smtp_from=cfg.get("smtp_from", ""),
                recipients=recipients,
                subject="Cost Intelligence Test",
                body="This is a test alert from Cost Intelligence.",
            )
            console.print(f"  Email test: {'[green]sent[/green]' if ok else '[red]failed[/red]'}")
    elif action == "check":
        result = check_and_alert()
        if result["triggered"]:
            console.print(f"[red]⚠[/red] {result['message']}")
            console.print(f"Alert sent: {result['alert_sent']}")
        else:
            console.print("[green]✓[/green] Budget within threshold")
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(code=1)

@app.command(name="check-budget")
def check_budget_cmd():
    """Cron entrypoint: check budget and send alerts if needed.
    
    Usage in crontab:
        0 9 * * * cost-intel check-budget
    """
    result = check_and_alert()
    if result["triggered"]:
        console.print(f"[red]ALERT:[/red] {result['message']}")
        raise typer.Exit(code=1)
    else:
        console.print("[green]✓[/green] Budget OK")
```

**Step 5: Update config.py — add alert config keys**

Add to the config.yaml schema and `get_config()` defaults:

```yaml
# ~/.cost-intel/config.yaml
# ... existing keys ...

# Alert configuration
slack_webhook_url: ""          # Slack incoming webhook URL
smtp_host: ""                  # SMTP server hostname
smtp_from: ""                  # From email address
alert_recipients: []           # List of email addresses
```

**Step 6: Run test to verify pass**

```bash
pytest tests/test_alerts.py -v
```
Expected: 6 passed

**Step 7: Commit**

```bash
git add src/cost_intel/alerts.py src/cost_intel/cli.py src/cost_intel/config.py tests/test_alerts.py
git commit -m "feat: budget alerts — Slack webhook + email dispatch"
```

---

## Phase 4: Multi-Agent + Advanced (Weeks 10-12)

> **Deliverable:** Multi-agent cost intelligence via OpenTelemetry.

### Task 4.0: Schema Migration — Add OTel Trace Columns

**Objective:** Add `trace_id`, `span_id`, `parent_span_id` columns to `cost_runs` via a proper schema migration. This is a new task required because the original plan had no migration strategy and the OTel columns were entirely missing.

**Audit fixes applied:**
- Migration 003 with `trace_id`, `span_id`, `parent_span_id` columns
- Indexes on `trace_id` and `parent_span_id`
- Migration runner integrated into `init_db()`

**Files:**
- Create: `src/cost_intel/migrations/003_add_trace_ids.sql`
- Modify: `src/cost_intel/db.py` (add migration runner)
- Test: `tests/test_migrations.py`

**Step 1: Write failing test**

```python
# tests/test_migrations.py
import pytest
from cost_intel.db import get_connection, init_db

def test_migration_003_adds_trace_columns(tmp_cost_intel_home):
    init_db()
    with get_connection() as conn:
        # Verify columns exist
        cursor = conn.execute("PRAGMA table_info(cost_runs)")
        cols = {row["name"] for row in cursor.fetchall()}
        assert "trace_id" in cols
        assert "span_id" in cols
        assert "parent_span_id" in cols

def test_migration_003_adds_indexes(tmp_cost_intel_home):
    init_db()
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_cost_runs_trace%'"
        )
        indexes = {row["name"] for row in cursor.fetchall()}
        assert "idx_cost_runs_trace_id" in indexes
        assert "idx_cost_runs_parent_span" in indexes

def test_migration_idempotent(tmp_cost_intel_home):
    """Running init_db() twice must not fail."""
    init_db()
    init_db()  # Should not raise
```

**Step 2: Run test to verify failure**

```bash
pytest tests/test_migrations.py -v
```
Expected: FAIL — columns don't exist

**Step 3: Create migration file**

```sql
-- src/cost_intel/migrations/003_add_trace_ids.sql
-- Add OpenTelemetry trace columns to cost_runs

ALTER TABLE cost_runs ADD COLUMN trace_id TEXT;
ALTER TABLE cost_runs ADD COLUMN span_id TEXT;
ALTER TABLE cost_runs ADD COLUMN parent_span_id TEXT;

CREATE INDEX IF NOT EXISTS idx_cost_runs_trace_id ON cost_runs(trace_id);
CREATE INDEX IF NOT EXISTS idx_cost_runs_parent_span ON cost_runs(parent_span_id);
```

**Step 4: Add migration runner to db.py**

Add to `src/cost_intel/db.py`:

```python
import importlib.resources

_MIGRATION_DIR = pathlib.Path(__file__).parent / "migrations"


def _run_pending_migrations(conn):
    """Apply any pending schema migrations in order."""
    # Ensure schema_version table exists
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT DEFAULT (datetime('now'))
        )
        """
    )
    current = conn.execute(
        "SELECT MAX(version) AS v FROM schema_version"
    ).fetchone()
    current_version = current["v"] if current and current["v"] is not None else 0

    # List and apply pending migrations
    migration_files = sorted(_MIGRATION_DIR.glob("*.sql"))
    for mig_file in migration_files:
        version = int(mig_file.stem.split("_")[0])
        if version > current_version:
            sql = mig_file.read_text()
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)", (version,)
            )
            conn.commit()


def init_db() -> sqlite3.Connection:
    """Initialize the database schema. Idempotent, runs pending migrations."""
    conn = get_connection()
    conn.executescript(_SCHEMA)
    _run_pending_migrations(conn)
    return conn
```

**Step 5: Run test to verify pass**

```bash
pytest tests/test_migrations.py -v
```
Expected: 3 passed

**Step 6: Commit**

```bash
git add src/cost_intel/migrations/003_add_trace_ids.sql src/cost_intel/db.py tests/test_migrations.py
git commit -m "feat: migration 003 — add trace_id, span_id, parent_span_id to cost_runs"
```

---

### Task 4.1: OpenTelemetry Span Ingestion (Fixed)

**Objective:** Ingest OTel spans storing `trace_id`, `span_id`, `parent_span_id` in `cost_runs`. Honor caller-supplied `run_id` for the span path.

**Audit fixes applied:**
- `ingest_span()` stores `trace_id`, `span_id`, `parent_span_id` in `cost_runs`
- `ingest_span()` passes caller-supplied `run_id` (the `span_id`) instead of generating a fresh UUID
- `record_run()` extended to accept and store trace columns

**Files:**
- Create: `src/cost_intel/otel.py`
- Modify: `src/cost_intel/record.py` (extend `record_run` signature)
- Test: `tests/test_otel.py`

**Step 1: Write failing test**

```python
# tests/test_otel.py
import pytest
from cost_intel.otel import ingest_span

def test_ingest_span_creates_run_with_span_id(tmp_cost_intel_home):
    """ingest_span must store the span_id as run_id so the caller can look it up."""
    from cost_intel.db import init_db
    init_db()
    run_id = ingest_span(
        span_id="span-1",
        trace_id="trace-1",
        agent_name="summarizer",
        model_id="openai/gpt-4o",
        input_tokens=100,
        output_tokens=50,
        parent_span_id=None,
    )
    assert run_id == "span-1"
    from cost_intel.record import get_run
    run = get_run("span-1")
    assert run is not None
    assert run["label"] == "summarizer"
    assert run["trace_id"] == "trace-1"
    assert run["span_id"] == "span-1"
    assert run["parent_span_id"] is None

def test_ingest_span_with_parent(tmp_cost_intel_home):
    from cost_intel.db import init_db
    init_db()
    ingest_span(
        span_id="span-child",
        trace_id="trace-1",
        agent_name="executor",
        model_id="openai/gpt-4o",
        input_tokens=200,
        output_tokens=100,
        parent_span_id="span-parent",
    )
    from cost_intel.record import get_run
    run = get_run("span-child")
    assert run["parent_span_id"] == "span-parent"
    assert run["trace_id"] == "trace-1"

def test_ingest_span_returns_run_id(tmp_cost_intel_home):
    from cost_intel.db import init_db
    init_db()
    result = ingest_span(
        span_id="span-42",
        trace_id="trace-99",
        agent_name="reviewer",
        model_id="openai/gpt-4o",
        input_tokens=50,
        output_tokens=25,
    )
    assert result == "span-42"
```

**Step 2: Run test to verify failure**

```bash
pytest tests/test_otel.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Extend `record_run` in record.py**

Add trace columns to `record_run`:

```python
# Add to record.py record_run signature:
def record_run(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    label: str = "",
    run_type: str = "api_call",
    latency_ms: Optional[int] = None,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    provider: str = "",
    raw_response: Optional[str] = None,
    # OTel trace fields
    run_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
) -> str:
    """Record a cost run. Returns run_id."""
    from cost_intel.db import get_connection
    from cost_intel.pricing import _compute_cost
    import uuid

    resolved_run_id = run_id or str(uuid4())
    now = datetime.utcnow().isoformat() + "Z"

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO cost_runs
                (run_id, run_type, label, model_id, started_at, finished_at,
                 trace_id, span_id, parent_span_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_run_id, run_type, label, model_id, now, now,
                trace_id, span_id, parent_span_id,
            ),
        )
        cost = _compute_cost(conn, model_id, input_tokens, output_tokens,
                             cache_read_tokens, cache_write_tokens)
        conn.execute(
            """
            INSERT INTO cost_run_calls
                (run_id, sequence, provider, model, input_tokens, output_tokens,
                 cache_read_tokens, cache_write_tokens, call_cost, latency_ms, raw_response)
            VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolved_run_id, provider or model_id.split("/")[0],
                model_id, input_tokens, output_tokens,
                cache_read_tokens, cache_write_tokens,
                cost, latency_ms,
                raw_response[:4096] if raw_response else None,
            ),
        )
    return resolved_run_id
```

**Step 4: Write otel.py**

```python
# src/cost_intel/otel.py
"""OpenTelemetry span ingestion for multi-agent cost allocation."""

from typing import Optional

from cost_intel.record import record_run


def ingest_span(
    span_id: str,
    trace_id: str,
    agent_name: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    parent_span_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> str:
    """Ingest an OTel span as a cost run. Returns run_id (= span_id).

    The caller-supplied span_id is used as the run_id so that
    get_trace_cost() can look up spans by their OTel identity.
    """
    return record_run(
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        label=agent_name,
        run_type="agent_task",
        latency_ms=latency_ms,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        run_id=span_id,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
    )
```

**Step 5: Run test to verify pass**

```bash
pytest tests/test_otel.py -v
```
Expected: 3 passed

**Step 6: Commit**

```bash
git add src/cost_intel/otel.py src/cost_intel/record.py tests/test_otel.py
git commit -m "feat: OTel span ingestion — stores trace_id, span_id, parent_span_id"
```

---

### Task 4.2: Trace Cost Breakdown — `cost-intel trace-cost` (Fixed)

**Objective:** Show cost breakdown by agent in a workflow trace. Filter by `trace_id`, walk the `parent_span_id` graph, roll up costs, and compute CPQP at each level.

**Audit fixes applied:**
- `get_trace_cost()` filters `WHERE trace_id = ?` (was returning all `agent_task` rows globally)
- Walks the `parent_span_id` graph to roll costs up to roots
- Computes CPQP at each level

**Files:**
- Modify: `src/cost_intel/otel.py`
- Modify: `src/cost_intel/cli.py`
- Test: `tests/test_otel.py` (add trace cost tests)

**Step 1: Add failing tests**

```python
def test_trace_cost_filters_by_trace_id(tmp_cost_intel_home):
    """get_trace_cost must filter WHERE trace_id = ?, not return all rows."""
    from cost_intel.db import init_db
    from cost_intel.otel import ingest_span, get_trace_cost
    init_db()
    # Two traces
    ingest_span("s1", "trace-A", "planner", "openai/gpt-4o", 200, 100)
    ingest_span("s2", "trace-A", "executor", "openai/gpt-4o", 500, 250)
    ingest_span("s3", "trace-B", "other", "openai/gpt-4o", 999, 999)
    cost = get_trace_cost("trace-A")
    assert cost["trace_id"] == "trace-A"
    assert cost["total_runs"] == 2
    # trace-B must not appear
    agent_labels = {a["label"] for a in cost["agents"]}
    assert "other" not in agent_labels

def test_trace_cost_rolls_up_parent_spans(tmp_cost_intel_home):
    """Child span costs must roll up into parent totals."""
    from cost_intel.db import init_db
    from cost_intel.otel import ingest_span, get_trace_cost
    init_db()
    # Root span
    ingest_span("root", "trace-1", "orchestrator", "openai/gpt-4o", 100, 50,
                parent_span_id=None)
    # Child spans
    ingest_span("child-1", "trace-1", "planner", "openai/gpt-4o", 200, 100,
                parent_span_id="root")
    ingest_span("child-2", "trace-1", "executor", "openai/gpt-4o", 300, 150,
                parent_span_id="root")
    cost = get_trace_cost("trace-1")
    assert cost["total_runs"] == 3
    # Find the orchestrator — it should include child costs in rolled_up_cost
    orchestrator = next(a for a in cost["agents"] if a["label"] == "orchestrator")
    assert orchestrator["rolled_up_cost"] > orchestrator["own_cost"]

def test_trace_cost_with_cpqp(tmp_cost_intel_home):
    """CPQP must be computed at each level when quality scores exist."""
    from cost_intel.db import init_db
    from cost_intel.otel import ingest_span, get_trace_cost
    from cost_intel.quality import import_score
    init_db()
    ingest_span("s1", "trace-1", "agent-a", "openai/gpt-4o", 1000, 500)
    ingest_span("s2", "trace-1", "agent-b", "openai/gpt-4o", 200, 100)
    import_score("s1", score=0.5, source="test")
    import_score("s2", score=0.9, source="test")
    cost = get_trace_cost("trace-1")
    agent_a = next(a for a in cost["agents"] if a["label"] == "agent-a")
    agent_b = next(a for a in cost["agents"] if a["label"] == "agent-b")
    # agent-a: cost=7.5, score=0.5 -> CPQP = 15.0
    # agent-b: cost=2.5, score=0.9 -> CPQP ≈ 2.78
    assert agent_a["cpqp"] == 15.0
    assert abs(agent_b["cpqp"] - 2.7778) < 0.01
```

**Step 2: Run test to verify failure**

```bash
pytest tests/test_otel.py::test_trace_cost_filters_by_trace_id -v
```
Expected: FAIL — `get_trace_cost` not defined or wrong behavior

**Step 3: Add to otel.py**

```python
def get_trace_cost(trace_id: str) -> dict:
    """Get cost breakdown for a trace, with span-tree roll-up and CPQP.

    Returns:
        {
            "trace_id": str,
            "agents": [
                {
                    "run_id": str,
                    "label": str,
                    "model_id": str,
                    "own_cost": float,       # cost of this span alone
                    "rolled_up_cost": float, # own_cost + all descendants
                    "input_tokens": int,
                    "output_tokens": int,
                    "combined_score": float | None,
                    "cpqp": float | None,
                    "parent_span_id": str | None,
                    "depth": int,
                },
                ...
            ],
            "total_runs": int,
            "total_cost": float,      # sum of own_cost (no double counting)
            "total_rolled_cost": float,  # same as total_cost for flat sum
            "total_input_tokens": int,
            "total_output_tokens": int,
        }
    """
    with get_connection() as conn:
        # Fetch all runs for this trace
        rows = conn.execute(
            """
            SELECT
                cr.run_id, cr.label, cr.model_id, cr.parent_span_id,
                cr.span_id,
                SUM(crc.call_cost) AS own_cost,
                SUM(crc.input_tokens) AS input_tokens,
                SUM(crc.output_tokens) AS output_tokens,
                qs.combined_score,
                CASE
                    WHEN qs.combined_score IS NULL THEN NULL
                    ELSE ROUND(
                        SUM(crc.call_cost) / MAX(qs.combined_score, 0.01), 4
                    )
                END AS cpqp
            FROM cost_runs cr
            JOIN cost_run_calls crc ON cr.run_id = crc.run_id
            LEFT JOIN quality_scores qs ON cr.run_id = qs.run_id
            WHERE cr.trace_id = ?
            GROUP BY cr.run_id
            ORDER BY cr.started_at ASC
            """,
            (trace_id,),
        ).fetchall()

        agents = [dict(r) for r in rows]
        agent_map = {a["run_id"]: a for a in agents}

        # Build children map
        children_map: dict[str, list[str]] = {}
        for a in agents:
            pid = a["parent_span_id"]
            if pid and pid in agent_map:
                children_map.setdefault(pid, []).append(a["run_id"])

        # Walk the tree to compute rolled_up_cost and depth
        def roll_up(run_id: str, depth: int = 0) -> float:
            agent = agent_map[run_id]
            agent["depth"] = depth
            child_cost = sum(
                roll_up(child_id, depth + 1)
                for child_id in children_map.get(run_id, [])
            )
            agent["rolled_up_cost"] = agent["own_cost"] + child_cost
            return agent["rolled_up_cost"]

        # Find roots (no parent or parent not in this trace)
        roots = [
            a for a in agents
            if a["parent_span_id"] is None
            or a["parent_span_id"] not in agent_map
        ]
        for root in roots:
            roll_up(root["run_id"], 0)

        # Any orphaned nodes (parent_span_id set but parent not in trace)
        for a in agents:
            if "depth" not in a:
                roll_up(a["run_id"], 0)

        total_cost = sum(a["own_cost"] for a in agents)
        total_input = sum(a["input_tokens"] for a in agents)
        total_output = sum(a["output_tokens"] for a in agents)

        return {
            "trace_id": trace_id,
            "agents": agents,
            "total_runs": len(agents),
            "total_cost": total_cost,
            "total_rolled_cost": total_cost,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
        }
```

**Step 4: Update cli.py**

```python
from cost_intel.otel import get_trace_cost

@app.command(name="trace-cost")
def trace_cost_cmd(
    trace_id: str = typer.Argument(..., help="Trace ID"),
):
    """Show cost breakdown by agent in a trace."""
    from rich.table import Table
    data = get_trace_cost(trace_id)
    table = Table(title=f"Trace Cost: {trace_id}")
    table.add_column("Agent", style="cyan")
    table.add_column("Model", max_width=25)
    table.add_column("Own Cost", justify="right")
    table.add_column("Rolled Up", justify="right")
    table.add_column("Input Tok", justify="right")
    table.add_column("Output Tok", justify="right")
    table.add_column("CPQP", justify="right")
    for agent in data["agents"]:
        indent = "  " * agent.get("depth", 0)
        table.add_row(
            f"{indent}{agent['label']}",
            agent["model_id"],
            f"${agent['own_cost']:.4f}",
            f"${agent['rolled_up_cost']:.4f}",
            str(agent["input_tokens"]),
            str(agent["output_tokens"]),
            f"${agent['cpqp']:.4f}" if agent.get("cpqp") is not None else "N/A",
        )
    console.print(table)
    console.print(
        f"Total: [bold]${data['total_cost']:.4f}[/bold] "
        f"across {data['total_runs']} spans"
    )
```

**Step 5: Run test to verify pass**

```bash
pytest tests/test_otel.py -v
```
Expected: All tests passed (including new ones)

**Step 6: Commit**

```bash
git add src/cost_intel/otel.py src/cost_intel/cli.py tests/test_otel.py
git commit -m "feat: trace cost breakdown — span-tree roll-up + CPQP per level"
```

---

### Task 4.3: Prompt Optimization Suggestions

**Objective:** Analyze top N highest-cost label prefixes and suggest prompt trimming patterns. This is a new task required by research §9 Phase 4 deliverable 4 ("Prompt optimization suggestions").

**Audit fixes applied:**
- New task with TDD steps
- Analyzes label prefixes to find high-cost patterns
- Suggests prompt trimming based on token/cost correlation

**Files:**
- Create: `src/cost_intel/prompt_opt.py`
- Modify: `src/cost_intel/cli.py`
- Test: `tests/test_prompt_opt.py`

**Step 1: Write failing test**

```python
# tests/test_prompt_opt.py
import pytest
from cost_intel.prompt_opt import analyze_prompt_patterns, suggest_trimming

def test_analyze_prompt_patterns(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    # High-cost "summarize" tasks
    for _ in range(5):
        record_run("openai/gpt-4o", 5000, 2000, label="summarize-doc")
    # Low-cost "classify" tasks
    for _ in range(5):
        record_run("openai/gpt-4o", 100, 50, label="classify-sentiment")
    results = analyze_prompt_patterns(top_n=5)
    assert len(results) > 0
    # summarize should be the most expensive prefix
    top = results[0]
    assert "summarize" in top["label_prefix"]
    assert top["avg_cost"] > 10.0

def test_suggest_trimming(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    # Very high input tokens → should suggest trimming
    for _ in range(3):
        record_run("openai/gpt-4o", 10000, 500, label="summarize-long")
    suggestions = suggest_trimming(threshold_tokens=5000)
    assert len(suggestions) > 0
    assert suggestions[0]["avg_input_tokens"] > 5000
    assert "trim" in suggestions[0]["suggestion"].lower() or "reduce" in suggestions[0]["suggestion"].lower()
```

**Step 2: Run test to verify failure**

```bash
pytest tests/test_prompt_opt.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/cost_intel/prompt_opt.py
"""Prompt optimization suggestions — identify high-cost label patterns."""

from typing import Optional

from cost_intel.db import get_connection


def analyze_prompt_patterns(top_n: int = 10) -> list[dict]:
    """Analyze top N highest-cost label prefixes.

    Groups runs by label prefix (first word of label) and computes
    aggregate cost statistics. Returns sorted by avg_cost descending.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                CASE
                    WHEN cr.label LIKE '%-%' THEN SUBSTR(cr.label, 1, INSTR(cr.label, '-') - 1)
                    WHEN cr.label LIKE '%_%' THEN SUBSTR(cr.label, 1, INSTR(cr.label, '_') - 1)
                    ELSE COALESCE(cr.label, '(unlabeled)')
                END AS label_prefix,
                COUNT(*) AS total_runs,
                SUM(crc.call_cost) AS total_cost,
                AVG(crc.call_cost) AS avg_cost,
                AVG(crc.input_tokens) AS avg_input_tokens,
                AVG(crc.output_tokens) AS avg_output_tokens,
                MIN(crc.call_cost) AS min_cost,
                MAX(crc.call_cost) AS max_cost
            FROM cost_runs cr
            JOIN cost_run_calls crc ON cr.run_id = crc.run_id
            GROUP BY label_prefix
            HAVING total_runs >= 2
            ORDER BY avg_cost DESC
            LIMIT ?
            """,
            (top_n,),
        ).fetchall()
        return [dict(r) for r in rows]


def suggest_trimming(threshold_tokens: int = 3000) -> list[dict]:
    """Suggest prompt trimming for high-input-token patterns.

    Finds label prefixes where avg input tokens exceed the threshold
    and generates actionable suggestions.
    """
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                cr.label,
                COUNT(*) AS runs,
                AVG(crc.input_tokens) AS avg_input_tokens,
                AVG(crc.call_cost) AS avg_cost,
                AVG(crc.output_tokens) AS avg_output_tokens
            FROM cost_runs cr
            JOIN cost_run_calls crc ON cr.run_id = crc.run_id
            WHERE crc.input_tokens > ?
            GROUP BY cr.label
            HAVING runs >= 2
            ORDER BY avg_cost DESC
            """,
            (threshold_tokens,),
        ).fetchall()

        suggestions = []
        for row in rows:
            avg_in = row["avg_input_tokens"]
            suggestion = {
                "label": row["label"],
                "runs": row["runs"],
                "avg_input_tokens": avg_in,
                "avg_cost": row["avg_cost"],
                "suggestion": (
                    f"Label '{row['label']}' averages {int(avg_in)} input tokens "
                    f"(${row['avg_cost']:.4f}/run). Consider: "
                    f"(1) trimming system prompt, "
                    f"(2) using a cheaper model for this task, "
                    f"(3) caching repeated context, "
                    f"(4) splitting into smaller sub-tasks."
                ),
            }
            suggestions.append(suggestion)
        return suggestions
```

**Step 4: Update cli.py**

```python
from cost_intel.prompt_opt import analyze_prompt_patterns, suggest_trimming

@app.command(name="prompt-opt")
def prompt_opt_cmd(
    top_n: int = typer.Option(10, "--top-n", help="Number of top patterns to show"),
    threshold_tokens: int = typer.Option(
        3000, "--threshold-tokens", help="Input token threshold for trimming suggestions"
    ),
):
    """Analyze prompt patterns and suggest optimizations."""
    from rich.table import Table

    console.print("[bold]Top Cost Patterns by Label Prefix[/bold]")
    patterns = analyze_prompt_patterns(top_n=top_n)
    table = Table()
    table.add_column("Prefix", style="cyan")
    table.add_column("Runs", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Avg Input Tok", justify="right")
    table.add_column("Total Cost", justify="right")
    for p in patterns:
        table.add_row(
            p["label_prefix"],
            str(p["total_runs"]),
            f"${p['avg_cost']:.4f}",
            f"{int(p['avg_input_tokens'])}",
            f"${p['total_cost']:.4f}",
        )
    console.print(table)

    console.print(f"\n[bold]Trimming Suggestions (>{threshold_tokens} avg input tokens)[/bold]")
    suggestions = suggest_trimming(threshold_tokens=threshold_tokens)
    if not suggestions:
        console.print("[green]No patterns exceed the threshold.[/green]")
    else:
        for s in suggestions:
            console.print(f"  • {s['suggestion']}")
```

**Step 5: Run test to verify pass**

```bash
pytest tests/test_prompt_opt.py -v
```
Expected: 2 passed

**Step 6: Commit**

```bash
git add src/cost_intel/prompt_opt.py src/cost_intel/cli.py tests/test_prompt_opt.py
git commit -m "feat: prompt optimization suggestions — label pattern analysis"
```

---

### Task 4.4: Budget Enforcement / Hard-Stop

**Objective:** Implement `cost-intel guard` mode that returns non-zero before issuing a new API call when the monthly budget is exceeded. This is a new task required by research §9 Phase 4 deliverable 5 ("Budget enforcement (hard stops at threshold)").

**Audit fixes applied:**
- New `cost-intel guard` CLI command
- Checks budget before allowing work to proceed
- Returns exit code 1 when budget exceeded
- Can be used as a pre-flight check in scripts

**Files:**
- Create: `src/cost_intel/guard.py`
- Modify: `src/cost_intel/cli.py`
- Test: `tests/test_guard.py`

**Step 1: Write failing test**

```python
# tests/test_guard.py
import pytest
from cost_intel.guard import check_guard

def test_guard_allows_when_under_budget(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.trends import set_budget
    init_db()
    set_budget(monthly=1000, alert_threshold=80)
    # No spending
    allowed, msg = check_guard()
    assert allowed is True

def test_guard_blocks_when_budget_exceeded(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.trends import set_budget
    init_db()
    set_budget(monthly=0, alert_threshold=0)  # $0 budget → always exceeded
    allowed, msg = check_guard()
    assert allowed is False
    assert "budget" in msg.lower()

def test_guard_no_budget_set(tmp_cost_intel_home):
    from cost_intel.db import init_db
    init_db()
    # No budget configured → guard allows (no constraint)
    allowed, msg = check_guard()
    assert allowed is True

def test_guard_with_custom_threshold(tmp_cost_intel_home):
    from cost_intel.db import init_db
    from cost_intel.trends import set_budget
    init_db()
    set_budget(monthly=100, alert_threshold=50)
    # No spending → under 50%
    allowed, msg = check_guard(threshold_override=0.5)
    assert allowed is True
```

**Step 2: Run test to verify failure**

```bash
pytest tests/test_guard.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# src/cost_intel/guard.py
"""Budget enforcement — hard-stop guard for API calls."""

from typing import Optional

from cost_intel.trends import get_budget_status


def check_guard(threshold_override: Optional[float] = None) -> tuple[bool, str]:
    """Check if the monthly budget allows new API calls.

    Args:
        threshold_override: If set, use this threshold (0.0-1.0) instead of
            the configured alert_threshold.

    Returns:
        (allowed, message) — allowed=False means budget exceeded, do not proceed.
    """
    status = get_budget_status()

    if not status["budget_set"]:
        return True, "No budget configured — guard allows"

    effective_threshold = threshold_override if threshold_override is not None else status["alert_threshold"]
    percent_used = status["percent_used"]

    if percent_used >= effective_threshold:
        return (
            False,
            f"Budget exceeded: ${status['spent_this_month']:.2f} spent "
            f"of ${status['monthly_budget']:.2f} monthly budget "
            f"({percent_used}% >= {effective_threshold}% threshold). "
            f"API call blocked.",
        )

    return (
        True,
        f"Budget OK: ${status['spent_this_month']:.2f} spent "
        f"of ${status['monthly_budget']:.2f} ({percent_used}%)",
    )
```

**Step 4: Update cli.py**

```python
from cost_intel.guard import check_guard

@app.command(name="guard")
def guard_cmd(
    threshold: Optional[float] = typer.Option(
        None, "--threshold", "-t",
        help="Override alert threshold (0.0-1.0, e.g. 0.8 for 80%)"
    ),
):
    """Budget enforcement guard. Returns non-zero exit if budget exceeded.

    Use as a pre-flight check in scripts before issuing API calls:

        #!/bin/bash
        if ! cost-intel guard; then
            echo "Budget exceeded — skipping API call"
            exit 1
        fi
        # ... proceed with API call ...
    """
    allowed, msg = check_guard(threshold_override=threshold)
    if allowed:
        console.print(f"[green]✓[/green] {msg}")
    else:
        console.print(f"[red]✗[/red] {msg}")
    raise typer.Exit(code=0 if allowed else 1)
```

**Step 5: Run test to verify pass**

```bash
pytest tests/test_guard.py -v
```
Expected: 4 passed

**Step 6: Commit**

```bash
git add src/cost_intel/guard.py src/cost_intel/cli.py tests/test_guard.py
git commit -m "feat: budget enforcement guard — hard-stop when budget exceeded"
```

---

## Phase 3 Success Criteria

Before considering Phase 3 complete:
1. `cost-intel gate` exits 0/1 correctly in CI with `--window 7d` (string parsing)
2. `cost-intel gate --max-waste-index` actually checks waste index
3. `cost-intel gate` with `max_avg_cpqp` but no quality data returns informative failure
4. `cost-intel gate --format json` produces valid JSON output
5. `cost-intel alert test` verifies Slack/email configuration
6. `cost-intel check-budget` sends alerts when threshold exceeded
7. GitHub Actions example works in a real repo
8. All tests pass

## Phase 4 Success Criteria

Before considering Phase 4 complete:
1. `ingest_span()` stores `trace_id`, `span_id`, `parent_span_id` in `cost_runs`
2. `get_trace_cost(trace_id)` filters by trace_id (not global)
3. `get_trace_cost()` rolls up child costs into parents
4. CPQP computed at each span level when quality scores exist
5. `cost-intel prompt-opt` identifies high-cost label patterns
6. `cost-intel guard` blocks when budget exceeded, allows when under
7. Migration 003 applies cleanly on existing databases
8. All tests pass

---

*Full plan revised: June 2 2026*
*67 audit findings addressed (30 LLM + 37 Droid)*
*Plan ready for re-audit*
