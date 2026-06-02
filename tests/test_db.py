"""Tests for database layer and migration framework."""

from cost_intel.db import connect, get_connection, init_db
from cost_intel.migration_runner import (
    get_current_version,
)


class TestMigrations:
    """Tests for the migration runner."""

    def test_initial_version_is_zero(self, tmp_cost_intel_home):
        """Before any migrations applied, version should be 0."""
        conn = get_connection()
        ver = get_current_version(conn)
        assert ver == 0
        conn.close()

    def test_migration_001_creates_base_tables(self, tmp_cost_intel_home):
        """Migration 001 creates all Phase 1 tables."""
        conn = init_db()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r["name"] for r in tables}
        assert "cost_runs" in table_names
        assert "cost_run_calls" in table_names
        assert "model_pricing" in table_names
        assert "schema_version" in table_names
        assert "config" in table_names
        conn.close()

    def test_migration_version_is_one_after_001(self, tmp_cost_intel_home):
        """After migration 001, schema version is 1."""
        conn = init_db()
        ver = get_current_version(conn)
        assert ver >= 1
        conn.close()

    def test_init_db_is_idempotent(self, tmp_cost_intel_home):
        """Running init_db twice doesn't fail or duplicate data."""
        conn1 = init_db()
        conn1.close()
        conn2 = init_db()
        # Should still have exactly the same tables
        tables = conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r["name"] for r in tables}
        assert "cost_runs" in table_names
        conn2.close()

    def test_model_pricing_has_composite_pk(self, tmp_cost_intel_home):
        """model_pricing primary key is (model_id, effective_date)."""
        conn = init_db()
        # Insert two rows for same model on different dates
        conn.execute(
            "INSERT INTO model_pricing "
            "(model_id, provider, input_price_per_1k_tokens, "
            "output_price_per_1k_tokens, effective_date, is_current, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("openai/gpt-4o", "openai", 30.0, 60.0, "2026-01-01", 0, "openrouter"),
        )
        conn.execute(
            "INSERT INTO model_pricing "
            "(model_id, provider, input_price_per_1k_tokens, "
            "output_price_per_1k_tokens, effective_date, is_current, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("openai/gpt-4o", "openai", 25.0, 50.0, "2026-06-01", 1, "openrouter"),
        )
        conn.commit()
        rows = conn.execute(
            "SELECT COUNT(*) as cnt FROM model_pricing WHERE model_id = ?",
            ("openai/gpt-4o",),
        ).fetchone()
        assert rows["cnt"] == 2
        conn.close()


class TestConnection:
    """Tests for connection management."""

    def test_connection_has_busy_timeout(self, tmp_cost_intel_home):
        """Connection has busy_timeout set to 5000ms."""
        conn = get_connection()
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert timeout == 5000
        conn.close()

    def test_connection_has_wal_mode(self, tmp_cost_intel_home):
        """Connection uses WAL journal mode."""
        conn = get_connection()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()

    def test_connection_has_foreign_keys(self, tmp_cost_intel_home):
        """Connection has foreign keys enabled."""
        conn = get_connection()
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1
        conn.close()

    def test_connect_contextmanager_commits(self, tmp_cost_intel_home):
        """The connect() contextmanager commits on success."""
        init_db()  # Ensure schema exists
        with connect() as conn:
            conn.execute(
                "INSERT INTO config (key, value) VALUES (?, ?)",
                ("test_key", "test_value"),
            )
        # Verify data persisted
        with connect() as conn:
            row = conn.execute(
                "SELECT value FROM config WHERE key = ?", ("test_key",)
            ).fetchone()
        assert row is not None
        assert row["value"] == "test_value"

    def test_connect_contextmanager_rolls_back_on_error(self, tmp_cost_intel_home):
        """The connect() contextmanager rolls back on exception."""
        init_db()
        try:
            with connect() as conn:
                conn.execute(
                    "INSERT INTO config (key, value) VALUES (?, ?)",
                    ("will_rollback", "yes"),
                )
                raise RuntimeError("force rollback")
        except RuntimeError:
            pass
        # Verify data was NOT persisted
        with connect() as conn:
            row = conn.execute(
                "SELECT value FROM config WHERE key = ?",
                ("will_rollback",),
            ).fetchone()
        assert row is None

    def test_cost_runs_table_structure(self, tmp_cost_intel_home):
        """cost_runs table has all expected columns."""
        conn = init_db()
        cols = conn.execute("PRAGMA table_info(cost_runs)").fetchall()
        col_names = {r["name"] for r in cols}
        assert "run_id" in col_names
        assert "run_type" in col_names
        assert "label" in col_names
        assert "model_id" in col_names
        assert "started_at" in col_names
        assert "finished_at" in col_names
        assert "status" in col_names
        assert "created_at" in col_names
        conn.close()

    def test_cost_run_calls_table_structure(self, tmp_cost_intel_home):
        """cost_run_calls table has all expected columns."""
        conn = init_db()
        cols = conn.execute("PRAGMA table_info(cost_run_calls)").fetchall()
        col_names = {r["name"] for r in cols}
        assert "call_id" in col_names
        assert "run_id" in col_names
        assert "sequence" in col_names
        assert "provider" in col_names
        assert "model" in col_names
        assert "input_tokens" in col_names
        assert "output_tokens" in col_names
        assert "cache_read_tokens" in col_names
        assert "cache_write_tokens" in col_names
        assert "call_cost" in col_names
        assert "latency_ms" in col_names
        assert "raw_response" in col_names
        conn.close()
