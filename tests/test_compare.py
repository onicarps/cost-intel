"""Tests for compare_models — model comparison with efficiency delta."""

from typer.testing import CliRunner

from cost_intel.cli import app
from cost_intel.compare import compare_models
from cost_intel.db import init_db
from cost_intel.pricing import upsert_pricing
from cost_intel.quality import import_score
from cost_intel.record import record_run

runner = CliRunner()


def test_compare_models_basic(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    upsert_pricing("anthropic/claude-sonnet-4", "anthropic", 3.0, 15.0)
    record_run("openai/gpt-4o", 1000, 500, label="summarize")
    record_run("anthropic/claude-sonnet-4", 800, 400, label="summarize")
    results = compare_models(label="summarize")
    assert len(results) == 2
    gpt = next(r for r in results if r["model_id"] == "openai/gpt-4o")
    claude = next(r for r in results if r["model_id"] == "anthropic/claude-sonnet-4")
    assert abs(gpt["total_cost"] - 7.5) < 0.001
    assert abs(claude["total_cost"] - 8.4) < 0.001


def test_compare_models_includes_cpqp_delta(tmp_cost_intel_home):
    """compare_models must report avg_cpqp and delta_cpqp."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    upsert_pricing("openai/gpt-4o-mini", "openai", 0.15, 0.6)
    rid1 = record_run("openai/gpt-4o", 1000, 500, label="summarize")
    import_score(rid1, score=0.8, source="test")
    rid2 = record_run("openai/gpt-4o-mini", 1000, 500, label="summarize")
    import_score(rid2, score=0.7, source="test")
    results = compare_models(label="summarize")
    for r in results:
        assert "avg_cpqp" in r
    deltas = [r.get("delta_cpqp") for r in results]
    assert any(d is not None for d in deltas)
    # Best model has delta=0
    bests = [r for r in results if r.get("delta_cpqp") == 0.0]
    assert len(bests) >= 1


def test_compare_models_filter_returns_empty_with_warning(tmp_cost_intel_home):
    """compare_models with no matches returns an empty list."""
    init_db()
    results = compare_models(label="never-existed")
    assert results == []


def test_compare_models_filter_by_models(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    upsert_pricing("anthropic/claude-sonnet-4", "anthropic", 3.0, 15.0)
    record_run("openai/gpt-4o", 100, 50, label="x")
    record_run("anthropic/claude-sonnet-4", 100, 50, label="x")
    results = compare_models(label="x", models=["openai/gpt-4o"])
    assert len(results) == 1
    assert results[0]["model_id"] == "openai/gpt-4o"


def test_compare_models_cli_warns_when_empty(tmp_cost_intel_home):
    """CLI prints a warning when the filter returns no results."""
    init_db()
    result = runner.invoke(app, ["compare-models", "--label", "no-such-label"])
    assert result.exit_code == 0
    assert (
        "no" in result.output.lower()
        or "warn" in result.output.lower()
        or "empty" in result.output.lower()
    )
