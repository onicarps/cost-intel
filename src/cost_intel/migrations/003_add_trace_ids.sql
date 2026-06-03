-- 003_add_trace_ids.sql — Phase 4 trace columns
-- Adds OpenTelemetry-compatible trace_id, span_id, parent_span_id
-- to cost_runs and indexes them for trace-cost roll-ups.

ALTER TABLE cost_runs ADD COLUMN trace_id TEXT;
ALTER TABLE cost_runs ADD COLUMN span_id TEXT;
ALTER TABLE cost_runs ADD COLUMN parent_span_id TEXT;

CREATE INDEX IF NOT EXISTS idx_cost_runs_trace_id ON cost_runs(trace_id);
CREATE INDEX IF NOT EXISTS idx_cost_runs_parent_span ON cost_runs(parent_span_id);
