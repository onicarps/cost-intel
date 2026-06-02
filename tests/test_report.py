"""Tests for report module — aggregate views and time-window filtering."""

from cost_intel.budget import get_budget_status, set_budget
from cost_intel.record import record_run
from cost_intel.report import (
    report_by_day,
    report_by_label,
    report_by_model,
    report_summary,
)


class TestReportSummary:
    """Tests for report_summary."""

    def test_summary_empty_db(self, tmp_cost_intel_home):
        """Summary on empty database returns zeros."""
        from cost_intel.db import init_db

        init_db()
        summary = report_summary()
        assert summary["total_runs"] == 0
        assert summary["total_cost"] == 0.0

    def test_summary_with_runs(self, tmp_cost_intel_home):
        """Summary aggregates runs and costs correctly."""
        from cost_intel.db import init_db

        init_db()
        from cost_intel.pricing import upsert_pricing

        upsert_pricing("openai/gpt-4o", "openai", 30.0, 60.0)

        record_run("openai/gpt-4o", 1000, 500, label="run-1")
        record_run("openai/gpt-4o", 2000, 1000, label="run-2")

        summary = report_summary()
        assert summary["total_runs"] == 2
        assert summary["total_cost"] == 60.0 + 120.0  # 30+30 + 60+60

    def test_summary_with_time_window(self, tmp_cost_intel_home):
        """Summary filters by time window (days)."""
        from cost_intel.db import get_connection, init_db

        init_db()
        from cost_intel.pricing import upsert_pricing

        upsert_pricing("openai/gpt-4o", "openai", 30.0, 60.0)

        # Insert a run with a very old timestamp
        conn = get_connection()
        conn.execute(
            "INSERT INTO cost_runs "
            "(run_id, run_type, model_id, started_at, finished_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "old-run-id",
                "api_call",
                "openai/gpt-4o",
                "2020-01-01 00:00:00",
                "2020-01-01 00:00:10",
                "completed",
            ),
        )
        conn.execute(
            "INSERT INTO cost_run_calls "
            "(run_id, sequence, provider, model, input_tokens, "
            "output_tokens, call_cost) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("old-run-id", 0, "openai", "openai/gpt-4o", 100, 50, 45.0),
        )
        conn.commit()
        conn.close()

        # Recent run
        record_run("openai/gpt-4o", 1000, 500, label="recent")

        # Summary with 1-day window should only include recent run
        summary = report_summary(days=1)
        assert summary["total_runs"] == 1

        # Summary with large window includes both
        summary_all = report_summary(days=3650)  # ~10 years
        assert summary_all["total_runs"] == 2


class TestReportByModel:
    """Tests for report_by_model."""

    def test_by_model(self, tmp_cost_intel_home):
        """Report groups runs by model."""
        from cost_intel.db import init_db

        init_db()
        from cost_intel.pricing import upsert_pricing

        upsert_pricing("openai/gpt-4o", "openai", 30.0, 60.0)
        upsert_pricing("anthropic/claude", "anthropic", 3.0, 15.0)

        record_run("openai/gpt-4o", 100, 50)
        record_run("openai/gpt-4o", 200, 100)
        record_run("anthropic/claude", 100, 50)

        by_model = report_by_model()
        assert len(by_model) == 2
        gpt = next(m for m in by_model if m["model_id"] == "openai/gpt-4o")
        assert gpt["run_count"] == 2
        claude = next(m for m in by_model if m["model_id"] == "anthropic/claude")
        assert claude["run_count"] == 1


class TestReportByLabel:
    """Tests for report_by_label."""

    def test_by_label(self, tmp_cost_intel_home):
        """Report groups runs by label."""
        from cost_intel.db import init_db

        init_db()
        record_run("test/model", 100, 50, label="summarize")
        record_run("test/model", 200, 100, label="summarize")
        record_run("test/model", 50, 25, label="translate")

        by_label_rows = report_by_label()
        assert len(by_label_rows) == 2
        summ = next(r for r in by_label_rows if r["label"] == "summarize")
        assert summ["run_count"] == 2


class TestReportByDay:
    """Tests for report_by_day."""

    def test_by_day(self, tmp_cost_intel_home):
        """Report groups runs by day."""
        from cost_intel.db import get_connection, init_db

        init_db()
        # Insert runs on different days
        conn = get_connection()
        for day, run_id in [("2026-06-01", "day1-run"), ("2026-06-02", "day2-run")]:
            conn.execute(
                "INSERT INTO cost_runs "
                "(run_id, run_type, model_id, started_at, finished_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    "api_call",
                    "test/model",
                    f"{day}T12:00:00+00:00",
                    f"{day}T12:00:10+00:00",
                    "completed",
                ),
            )
            conn.execute(
                "INSERT INTO cost_run_calls "
                "(run_id, sequence, provider, model, input_tokens, "
                "output_tokens, call_cost) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (run_id, 0, "test", "test/model", 100, 50, 1.0),
            )
        conn.commit()
        conn.close()

        by_day = report_by_day()
        assert len(by_day) == 2
        assert by_day[0]["run_count"] == 1


class TestBudget:
    """Tests for budget module."""

    def test_set_and_get_budget(self, tmp_cost_intel_home):
        """Set budget and retrieve status."""
        from cost_intel.db import init_db

        init_db()
        set_budget(monthly=500.0, alert_threshold=80)
        status = get_budget_status()
        assert status["budget_set"] is True
        assert status["monthly"] == 500.0
        assert status["alert_threshold"] == 80

    def test_budget_status_no_budget(self, tmp_cost_intel_home):
        """Budget status returns defaults when not set."""
        from cost_intel.db import init_db

        init_db()
        status = get_budget_status()
        assert status["budget_set"] is False
        assert status["monthly"] is None
        assert status["alert_threshold"] is None

    def test_budget_status_with_spending(self, tmp_cost_intel_home):
        """Budget status includes current spending info."""
        from cost_intel.db import init_db

        init_db()
        set_budget(monthly=500.0, alert_threshold=80)

        # Insert a run with today's date
        from cost_intel.pricing import upsert_pricing

        upsert_pricing("openai/gpt-4o", "openai", 30.0, 60.0)
        record_run("openai/gpt-4o", 100, 50)

        status = get_budget_status()
        assert status["budget_set"] is True
        assert status["spent"] > 0
