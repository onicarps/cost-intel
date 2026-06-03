"""Tests for migration 002 — quality_scores table + cost_run_cpqp view."""

from cost_intel.db import get_connection, init_db
from cost_intel.migration_runner import (
    apply_pending_migrations,
    get_current_version,
)


def test_migration_002_creates_quality_scores_table(tmp_cost_intel_home):
    """Migration 002 creates the quality_scores table with expected columns."""
    init_db()
    conn = get_connection()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    table_names = {r["name"] for r in tables}
    assert "quality_scores" in table_names

    cols = conn.execute("PRAGMA table_info(quality_scores)").fetchall()
    col_names = {r["name"] for r in cols}
    assert "score_id" in col_names
    assert "run_id" in col_names
    assert "source" in col_names
    assert "source_run_id" in col_names
    assert "combined_score" in col_names
    assert "eval_dimensions" in col_names
    assert "eval_weights" in col_names
    assert "notes" in col_names
    assert "imported_at" in col_names
    conn.close()


def test_migration_002_creates_cpqp_view(tmp_cost_intel_home):
    """Migration 002 creates the cost_run_cpqp view."""
    init_db()
    conn = get_connection()
    views = conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()
    view_names = {r["name"] for r in views}
    assert "cost_run_cpqp" in view_names
    conn.close()


def test_migration_002_version_is_two(tmp_cost_intel_home):
    """After migrations, the schema version is 2."""
    init_db()
    assert get_current_version() == 2


def test_migrations_are_idempotent(tmp_cost_intel_home):
    """Re-running migrations is a no-op (does not fail or duplicate)."""
    init_db()
    apply_pending_migrations()
    apply_pending_migrations()
    assert get_current_version() == 2


def test_quality_scores_check_constraint(tmp_cost_intel_home):
    """combined_score CHECK enforces 0.0-1.0 range."""
    import sqlite3

    init_db()
    conn = get_connection()
    # Insert a parent run
    conn.execute(
        "INSERT INTO cost_runs (run_id, run_type, started_at) "
        "VALUES (?, ?, datetime('now'))",
        ("test-run", "api_call"),
    )
    conn.commit()
    # Insert valid score
    conn.execute(
        "INSERT INTO quality_scores (run_id, source, combined_score) VALUES (?, ?, ?)",
        ("test-run", "test", 0.5),
    )
    conn.commit()
    # Out-of-range score raises
    raised = False
    try:
        conn.execute(
            "INSERT INTO quality_scores (run_id, source, combined_score) "
            "VALUES (?, ?, ?)",
            ("test-run", "test", 1.5),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raised = True
    assert raised, "CHECK constraint did not reject combined_score=1.5"
    conn.close()


def test_cpqp_view_returns_rating_column(tmp_cost_intel_home):
    """cost_run_cpqp view exposes the rating column with valid letter grades."""
    from cost_intel.pricing import upsert_pricing
    from cost_intel.record import record_run

    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    run_id = record_run("openai/gpt-4o", 100, 50, label="test")

    conn = get_connection()
    conn.execute(
        "INSERT INTO quality_scores (run_id, source, combined_score) VALUES (?, ?, ?)",
        (run_id, "test", 0.85),
    )
    conn.commit()

    rows = conn.execute(
        "SELECT * FROM cost_run_cpqp WHERE run_id = ?", (run_id,)
    ).fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert "rating" in row
    assert row["rating"] in ("A", "B", "C", "D", "F", "N/A")
    assert "cpqp" in row
    assert row["combined_score"] == 0.85
    conn.close()
