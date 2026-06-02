-- 001_initial.sql — Phase 1 base schema
-- Applied by migration_runner.py during init_db()

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS model_pricing (
    model_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    input_price_per_1k_tokens REAL,
    output_price_per_1k_tokens REAL,
    cache_read_price_per_1k_tokens REAL DEFAULT NULL,
    cache_write_price_per_1k_tokens REAL DEFAULT NULL,
    effective_date TEXT NOT NULL DEFAULT (date('now')),
    is_current BOOLEAN DEFAULT 1,
    source TEXT DEFAULT 'openrouter',
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (model_id, effective_date)
);

CREATE INDEX IF NOT EXISTS idx_pricing_current
    ON model_pricing(model_id, is_current);

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

CREATE INDEX IF NOT EXISTS idx_cost_runs_model
    ON cost_runs(model_id);
CREATE INDEX IF NOT EXISTS idx_cost_runs_date
    ON cost_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_cost_runs_type
    ON cost_runs(run_type);
CREATE INDEX IF NOT EXISTS idx_cost_runs_label
    ON cost_runs(label);

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

CREATE INDEX IF NOT EXISTS idx_calls_run
    ON cost_run_calls(run_id);

CREATE TABLE IF NOT EXISTS config (
    key TEXT PRIMARY KEY,
    value TEXT
);
