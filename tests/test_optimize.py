"""Tests for optimization (model routing, waste index, target CPQP)."""

from typer.testing import CliRunner

from cost_intel.cli import app
from cost_intel.db import init_db
from cost_intel.optimize import (
    get_runs_above_target_cpqp,
    get_waste_index,
    suggest_model_routing,
)
from cost_intel.pricing import upsert_pricing
from cost_intel.quality import import_score
from cost_intel.record import record_run

runner = CliRunner()


def test_suggest_model_routing(tmp_cost_intel_home):
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
    # Cheapest model should come first
    assert suggestions[0]["model_id"] == "openai/gpt-4o-mini"


def test_suggest_model_routing_min_runs(tmp_cost_intel_home):
    """min_runs filter excludes underused models."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    record_run("openai/gpt-4o", 100, 50, label="rare")
    suggestions = suggest_model_routing(label="rare", min_runs=5)
    assert suggestions == []


def test_get_waste_index_valid_sql(tmp_cost_intel_home):
    """get_waste_index must not crash (no SUM-in-WHERE bug)."""
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
    assert wi["waste_spend"] > 0


def test_get_waste_index_empty_db(tmp_cost_intel_home):
    """waste index is 0 for an empty DB."""
    init_db()
    wi = get_waste_index()
    assert wi["total_spend"] == 0
    assert wi["waste_spend"] == 0
    assert wi["waste_index"] == 0.0


def test_get_waste_index_target_cpqp(tmp_cost_intel_home):
    """waste index with target_cpqp counts runs above the target."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    rid = record_run("openai/gpt-4o", 1000, 500, label="t")
    import_score(rid, score=0.1, source="test")  # CPQP ~ 75
    wi = get_waste_index(target_cpqp=1.0)
    assert wi["waste_spend"] > 0


def test_get_runs_above_target_cpqp(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    rid = record_run("openai/gpt-4o", 1000, 500, label="t")
    import_score(rid, score=0.1, source="test")
    runs = get_runs_above_target_cpqp(1.0)
    assert any(r["run_id"] == rid for r in runs)


def test_optimize_cli_no_shadow_crash(tmp_cost_intel_home):
    """--suggest-model-routing must not crash with TypeError (bool shadowing)."""
    init_db()
    result = runner.invoke(app, ["optimize", "--suggest-model-routing"])
    assert "TypeError" not in result.output
    assert "not callable" not in result.output
    assert result.exit_code == 0


def test_optimize_target_cpqp(tmp_cost_intel_home):
    """--target-cpqp must show runs exceeding the target."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    rid = record_run("openai/gpt-4o", 1000, 500, label="my-test-task")
    import_score(rid, score=0.1, source="test")
    result = runner.invoke(app, ["optimize", "--target-cpqp", "1.0"])
    assert result.exit_code == 0
    assert "my-test-task" in result.output or rid[:8] in result.output


def test_optimize_default_shows_waste_index(tmp_cost_intel_home):
    """Default optimize shows the waste index table."""
    init_db()
    result = runner.invoke(app, ["optimize"])
    assert result.exit_code == 0
    assert "Waste Index" in result.output
