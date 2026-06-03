-- 002_add_quality.sql — Phase 2 schema
-- Adds quality_scores table and the cost_run_cpqp view with
-- percentile-based A/B/C/D/F ratings derived from PERCENT_RANK().

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
