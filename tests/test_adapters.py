"""Tests for quality score adapters (Eval Harness, Braintrust)."""

import sqlite3
from unittest.mock import MagicMock, patch

from cost_intel.adapters.braintrust import import_from_api
from cost_intel.adapters.eval_harness import import_from_db
from cost_intel.db import init_db
from cost_intel.pricing import upsert_pricing
from cost_intel.quality import get_cpqp
from cost_intel.record import record_run


def test_eval_harness_adapter_reads_results_table(tmp_cost_intel_home, tmp_path):
    """Eval Harness adapter reads from SQLite 'results' table."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50, label="test")

    eval_db = tmp_path / "eval.db"
    conn = sqlite3.connect(str(eval_db))
    conn.execute("CREATE TABLE results (run_id TEXT, score REAL, source TEXT)")
    conn.execute(
        "INSERT INTO results VALUES (?, ?, ?)",
        (run_id, 0.82, "eval_harness"),
    )
    conn.commit()
    conn.close()

    count = import_from_db(str(eval_db))
    assert count == 1
    row = get_cpqp(run_id)
    assert row is not None
    assert abs(row["combined_score"] - 0.82) < 0.001


def test_eval_harness_adapter_missing_table_returns_zero(tmp_cost_intel_home, tmp_path):
    """If neither 'results' nor 'eval_results' table exists, return 0."""
    init_db()
    eval_db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(eval_db))
    conn.execute("CREATE TABLE other (x INTEGER)")
    conn.commit()
    conn.close()
    assert import_from_db(str(eval_db)) == 0


def test_braintrust_adapter_imports_scores(tmp_cost_intel_home):
    """Braintrust adapter uses httpx.Client.get and imports scores."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50, label="test")

    experiments_resp = MagicMock()
    experiments_resp.status_code = 200
    experiments_resp.json.return_value = {"data": [{"id": "exp-1"}]}
    experiments_resp.raise_for_status.return_value = None

    events_resp = MagicMock()
    events_resp.status_code = 200
    events_resp.json.return_value = {
        "data": [{"run_id": run_id, "scores": {"quality": 0.78}}]
    }
    events_resp.raise_for_status.return_value = None

    mock_client = MagicMock()
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False
    mock_client.get.side_effect = [experiments_resp, events_resp]

    with patch("httpx.Client", return_value=mock_client):
        count = import_from_api(api_key="bt-test-key", project_id="test-project")

    assert count == 1
    row = get_cpqp(run_id)
    assert row is not None
    assert abs(row["combined_score"] - 0.78) < 0.001
