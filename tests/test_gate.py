"""Tests for the CI/CD cost gate."""

import json

from typer.testing import CliRunner

from cost_intel.budget import set_budget
from cost_intel.cli import app
from cost_intel.db import init_db
from cost_intel.gate import check_gate
from cost_intel.pricing import upsert_pricing
from cost_intel.quality import import_score
from cost_intel.record import record_run

runner = CliRunner()


def test_gate_passes_when_under_threshold(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50)
    import_score(run_id, score=0.9, source="test")
    passed, msg = check_gate(max_avg_cpqp=10.0, window_days=7)
    assert passed is True


def test_gate_fails_when_over_threshold(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 10000, 5000)
    import_score(run_id, score=0.01, source="test")
    passed, msg = check_gate(max_avg_cpqp=0.10, window_days=7)
    assert passed is False
    assert "CPQP" in msg


def test_gate_no_quality_data_returns_fail(tmp_cost_intel_home):
    """When max_avg_cpqp is set but no runs have quality scores, gate must
    fail with an informative message — not silently pass."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    record_run("openai/gpt-4o", 100, 50)
    passed, msg = check_gate(max_avg_cpqp=10.0, window_days=7)
    assert passed is False
    assert "No quality score data" in msg


def test_gate_waste_index_passes(tmp_cost_intel_home):
    init_db()
    passed, msg = check_gate(max_waste_index=0.20, window_days=7)
    assert passed is True


def test_gate_waste_index_fails(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    for i in range(9):
        rid = record_run("openai/gpt-4o", 10, 5, label=f"good-{i}")
        import_score(rid, score=0.95, source="test")
    waste_id = record_run("openai/gpt-4o", 10000, 5000, label="waste")
    import_score(waste_id, score=0.05, source="test")
    passed, msg = check_gate(max_waste_index=0.20, window_days=7)
    assert passed is False
    assert "Waste index" in msg


def test_gate_budget_check_no_budget(tmp_cost_intel_home):
    """With no budget configured, budget_check passes silently."""
    init_db()
    passed, msg = check_gate(budget_check=True)
    assert passed is True


def test_gate_budget_check(tmp_cost_intel_home):
    init_db()
    set_budget(monthly=100, alert_threshold=80)
    passed, msg = check_gate(budget_check=True)
    assert passed is True


def test_gate_budget_alert_triggered(tmp_cost_intel_home):
    init_db()
    set_budget(monthly=100, alert_threshold=0)
    passed, msg = check_gate(budget_check=True)
    assert passed is False
    assert "Budget" in msg


def test_gate_all_passed_default_message(tmp_cost_intel_home):
    init_db()
    passed, msg = check_gate()
    assert passed is True
    assert "passed" in msg.lower()


def test_gate_cli_passes(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50)
    import_score(run_id, score=0.9, source="test")
    result = runner.invoke(app, ["gate", "--max-avg-cpqp", "10.0", "--window", "7d"])
    assert result.exit_code == 0, result.output


def test_gate_cli_fails(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 10000, 5000)
    import_score(run_id, score=0.01, source="test")
    result = runner.invoke(app, ["gate", "--max-avg-cpqp", "0.10", "--window", "7d"])
    assert result.exit_code == 1


def test_gate_cli_json_format(tmp_cost_intel_home):
    init_db()
    result = runner.invoke(app, ["gate", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip())
    assert payload["passed"] is True
    assert "message" in payload


def test_gate_cli_window_string_accepted(tmp_cost_intel_home):
    """--window must accept '7d' style strings (regression for audit fix)."""
    init_db()
    result = runner.invoke(app, ["gate", "--window", "7d"])
    assert result.exit_code == 0
