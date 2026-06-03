"""Tests for quality score import, CPQP calculation, and waste detection."""

from cost_intel.db import init_db
from cost_intel.pricing import upsert_pricing
from cost_intel.quality import (
    compute_combined_score,
    get_all_cpqp,
    get_cpqp,
    get_waste_runs,
    import_score,
    import_scores_csv,
)
from cost_intel.record import record_run


def test_import_score_basic(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50, label="test")
    import_score(run_id, score=0.85, source="test")
    row = get_cpqp(run_id)
    assert row is not None
    assert row["combined_score"] == 0.85


def test_import_score_clamps_range(tmp_cost_intel_home):
    """Score must be clamped to [0.0, 1.0] before insert."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50)
    import_score(run_id, score=1.5, source="test")
    row = get_cpqp(run_id)
    assert row["combined_score"] == 1.0


def test_cpqp_division_by_zero_guard(tmp_cost_intel_home):
    """When combined_score=0, CPQP uses MAX(score, 0.01) floor."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 1000, 500)
    import_score(run_id, score=0.0, source="test")
    cpqp = get_cpqp(run_id)
    # Cost=0.0025+0.005=0.0075; score=0 → uses 0.01 floor → CPQP=0.75
    assert cpqp["cpqp"] == 0.75


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
    weights = {"a": 2.0, "b": 2.0}
    result = compute_combined_score(dims, weights)
    assert abs(result - 0.5) < 0.001


def test_compute_combined_score_empty_dimensions():
    assert compute_combined_score({}) == 0.0


def test_import_score_with_dimensions_computes_combined(tmp_cost_intel_home):
    """When eval_dimensions supplied and score is None, auto-compute."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50)
    dims = {"faithfulness": 0.8, "task_completion": 0.9}
    import_score(run_id, score=None, source="eval_harness", eval_dimensions=dims)
    row = get_cpqp(run_id)
    assert abs(row["combined_score"] - 0.85) < 0.001


def test_import_scores_csv_basic(tmp_cost_intel_home, tmp_path):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50, label="test")
    csv_file = tmp_path / "scores.csv"
    csv_file.write_text(f"run_id,score\n{run_id},0.75\n")
    count = import_scores_csv(str(csv_file), source="csv")
    assert count == 1
    row = get_cpqp(run_id)
    assert row["combined_score"] == 0.75


def test_import_scores_csv_with_mapping(tmp_cost_intel_home, tmp_path):
    """JSON column mapping remaps source columns."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50, label="test")
    csv_file = tmp_path / "scores.csv"
    csv_file.write_text(f"id,quality\n{run_id},0.75\n")
    count = import_scores_csv(
        str(csv_file),
        source="csv",
        mapping={"run_id": "id", "score": "quality"},
    )
    assert count == 1
    row = get_cpqp(run_id)
    assert row["combined_score"] == 0.75


def test_get_waste_runs_uses_percentile_rating(tmp_cost_intel_home):
    """Waste runs = rating D or F (top 25% CPQP), NOT cpqp > 0.50."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    for i in range(9):
        rid = record_run("openai/gpt-4o", 10, 5, label=f"good-{i}")
        import_score(rid, score=0.95, source="test")
    expensive_run = record_run("openai/gpt-4o", 10000, 5000, label="waste")
    import_score(expensive_run, score=0.05, source="test")
    waste = get_waste_runs()
    waste_ids = {w["run_id"] for w in waste}
    assert expensive_run in waste_ids


def test_get_all_cpqp_includes_rating(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50)
    import_score(run_id, score=0.85, source="test")
    results = get_all_cpqp()
    assert len(results) >= 1
    assert "rating" in results[0]
    assert results[0]["rating"] in ("A", "B", "C", "D", "F")


def test_get_all_cpqp_days_filter(tmp_cost_intel_home):
    """get_all_cpqp(days=N) filters by started_at within last N days."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50)
    import_score(run_id, score=0.85, source="test")
    results = get_all_cpqp(days=30)
    assert len(results) >= 1
