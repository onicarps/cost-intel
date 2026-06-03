"""Tests for the cpqp and waste CLI commands."""

from typer.testing import CliRunner

from cost_intel.cli import app
from cost_intel.db import init_db
from cost_intel.pricing import upsert_pricing
from cost_intel.quality import import_score
from cost_intel.record import record_run

runner = CliRunner()


def _seed_waste(n_good: int = 9) -> str:
    """Seed a tmp DB with `n_good` cheap+high-quality runs plus one waste run.

    Returns the run_id of the waste run.
    """
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    for i in range(n_good):
        rid = record_run("openai/gpt-4o", 10, 5, label=f"good-{i}")
        import_score(rid, score=0.95, source="test")
    waste_id = record_run("openai/gpt-4o", 10000, 5000, label="waste-task")
    import_score(waste_id, score=0.05, source="test")
    return waste_id


def test_cpqp_shows_rating_column(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50)
    import_score(run_id, score=0.85, source="test")
    result = runner.invoke(app, ["cpqp"])
    assert result.exit_code == 0, result.output
    assert "Rating" in result.output or "rating" in result.output.lower()


def test_cpqp_waste_only_flag(tmp_cost_intel_home):
    _seed_waste()
    result = runner.invoke(app, ["cpqp", "--waste-only"])
    assert result.exit_code == 0, result.output
    assert "waste" in result.output.lower() or "F" in result.output


def test_waste_command_uses_percentile(tmp_cost_intel_home):
    """waste command shows the table; never the old hardcoded $0.50 threshold."""
    _seed_waste()
    result = runner.invoke(app, ["waste"])
    assert result.exit_code == 0, result.output
    assert "Waste" in result.output
    assert "0.50" not in result.output


def test_cpqp_last_flag_parses_duration(tmp_cost_intel_home):
    """--last 7d must not crash with a type error."""
    init_db()
    result = runner.invoke(app, ["cpqp", "--last", "7d"])
    assert "not a valid integer" not in result.output
    assert result.exit_code == 0, result.output


def test_cpqp_no_quality_data(tmp_cost_intel_home):
    """cpqp with no quality data exits cleanly."""
    init_db()
    result = runner.invoke(app, ["cpqp"])
    assert result.exit_code == 0
