"""Tests for record module — cost run recording."""

from cost_intel.record import get_run, get_run_calls, record_run


class TestRecordRun:
    """Tests for record_run."""

    def test_basic_record(self, tmp_cost_intel_home):
        """Record a basic cost run and verify it's stored."""
        from cost_intel.db import init_db

        init_db()
        # Need pricing for cost computation
        from cost_intel.pricing import upsert_pricing

        upsert_pricing("openai/gpt-4o", "openai", 30.0, 60.0)

        run_id = record_run("openai/gpt-4o", 1000, 500, label="test-run")
        assert run_id is not None
        assert len(run_id) == 36  # UUID format

    def test_cost_computed_from_pricing(self, tmp_cost_intel_home):
        """Cost is computed from model pricing."""
        from cost_intel.db import get_connection, init_db

        init_db()
        from cost_intel.pricing import upsert_pricing

        upsert_pricing("openai/gpt-4o", "openai", 30.0, 60.0)

        run_id = record_run("openai/gpt-4o", 1000, 500, label="cost-test")

        conn = get_connection()
        call = conn.execute(
            "SELECT call_cost FROM cost_run_calls WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        # 1000/1000 * 30 + 500/1000 * 60 = 30 + 30 = 60
        assert call["call_cost"] == 60.0
        conn.close()

    def test_unknown_model_gets_zero_cost(self, tmp_cost_intel_home):
        """Unknown model (no pricing) gets cost=0."""
        from cost_intel.db import get_connection, init_db

        init_db()
        run_id = record_run("unknown/model", 100, 50)

        conn = get_connection()
        call = conn.execute(
            "SELECT call_cost FROM cost_run_calls WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert call["call_cost"] == 0.0
        conn.close()

    def test_cache_tokens_stored(self, tmp_cost_intel_home):
        """Cache tokens are recorded in cost_run_calls."""
        from cost_intel.db import get_connection, init_db

        init_db()
        from cost_intel.pricing import upsert_pricing

        upsert_pricing("anthropic/claude", "anthropic", 3.0, 15.0)

        run_id = record_run(
            "anthropic/claude",
            500,
            200,
            label="cache-test",
            cache_read_tokens=300,
            cache_write_tokens=100,
        )

        conn = get_connection()
        call = conn.execute(
            "SELECT cache_read_tokens, cache_write_tokens "
            "FROM cost_run_calls WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert call["cache_read_tokens"] == 300
        assert call["cache_write_tokens"] == 100
        conn.close()

    def test_raw_response_truncated(self, tmp_cost_intel_home):
        """raw_response is truncated to 4KB."""
        from cost_intel.db import get_connection, init_db

        init_db()
        long_response = "x" * 5000
        run_id = record_run(
            "test/model",
            10,
            5,
            raw_response=long_response,
        )

        conn = get_connection()
        call = conn.execute(
            "SELECT raw_response FROM cost_run_calls WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert len(call["raw_response"]) == 4096
        conn.close()

    def test_run_type_stored(self, tmp_cost_intel_home):
        """run_type is stored correctly."""
        from cost_intel.db import get_connection, init_db

        init_db()
        run_id = record_run("test/model", 10, 5, run_type="agent_task")

        conn = get_connection()
        run = conn.execute(
            "SELECT run_type FROM cost_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert run["run_type"] == "agent_task"
        conn.close()

    def test_label_stored(self, tmp_cost_intel_home):
        """Label is stored on the run."""
        from cost_intel.db import get_connection, init_db

        init_db()
        run_id = record_run("test/model", 10, 5, label="summarize-doc")

        conn = get_connection()
        run = conn.execute(
            "SELECT label FROM cost_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert run["label"] == "summarize-doc"
        conn.close()

    def test_latency_stored(self, tmp_cost_intel_home):
        """Latency is stored on the call."""
        from cost_intel.db import get_connection, init_db

        init_db()
        run_id = record_run("test/model", 10, 5, latency_ms=250)

        conn = get_connection()
        call = conn.execute(
            "SELECT latency_ms FROM cost_run_calls WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        assert call["latency_ms"] == 250
        conn.close()


class TestGetRun:
    """Tests for get_run and get_run_calls."""

    def test_get_run_returns_run_data(self, tmp_cost_intel_home):
        """get_run returns the run's data."""
        from cost_intel.db import init_db

        init_db()
        run_id = record_run("test/model", 10, 5, label="fetch-test")

        run = get_run(run_id)
        assert run is not None
        assert run["label"] == "fetch-test"
        assert run["model_id"] == "test/model"

    def test_get_run_calls_returns_calls(self, tmp_cost_intel_home):
        """get_run_calls returns the calls for a run."""
        from cost_intel.db import init_db

        init_db()
        run_id = record_run("test/model", 10, 5, provider="test")

        calls = get_run_calls(run_id)
        assert len(calls) == 1
        assert calls[0]["input_tokens"] == 10
        assert calls[0]["output_tokens"] == 5

    def test_get_run_nonexistent(self, tmp_cost_intel_home):
        """get_run returns None for nonexistent run."""
        from cost_intel.db import init_db

        init_db()
        assert get_run("nonexistent-id") is None
