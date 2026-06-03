"""Tests for CPQP trend analysis (week-over-week)."""

from typer.testing import CliRunner

from cost_intel.cli import app
from cost_intel.db import init_db
from cost_intel.pricing import upsert_pricing
from cost_intel.quality import import_score
from cost_intel.record import record_run
from cost_intel.trends import get_cpqp_trend

runner = CliRunner()


def test_get_cpqp_trend_returns_expected_keys(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    for i in range(5):
        rid = record_run("openai/gpt-4o", 100, 50, label=f"run-{i}")
        import_score(rid, score=0.8, source="test")
    trend = get_cpqp_trend()
    assert "this_window" in trend
    assert "prior_window" in trend
    assert "ratio" in trend
    assert isinstance(trend["ratio"], float)
    assert trend["this_window"] >= 0


def test_get_cpqp_trend_empty_db(tmp_cost_intel_home):
    """Empty database returns 0 for both windows and 0.0 ratio."""
    init_db()
    trend = get_cpqp_trend()
    assert trend["this_window"] == 0
    assert trend["prior_window"] == 0
    assert trend["ratio"] == 0.0


def test_trends_cli_metric_cpqp(tmp_cost_intel_home):
    """cost-intel trends --metric cpqp must work without crashing."""
    init_db()
    result = runner.invoke(app, ["trends", "--metric", "cpqp"])
    assert result.exit_code == 0, result.output
    assert "CPQP" in result.output or "cpqp" in result.output.lower()


def test_trends_cli_default_still_works(tmp_cost_intel_home):
    """The legacy trends behavior (spending) still works."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    record_run("openai/gpt-4o", 100, 50)
    result = runner.invoke(app, ["trends"])
    assert result.exit_code == 0


def test_trends_cli_days_option(tmp_cost_intel_home):
    """--days option works with cpqp metric."""
    init_db()
    result = runner.invoke(app, ["trends", "--metric", "cpqp", "--days", "14"])
    assert result.exit_code == 0
