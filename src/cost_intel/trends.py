"""Trend analysis — spending trends and week-over-week CPQP comparison."""

from typing import Optional

from cost_intel.db import get_connection


def get_cpqp_trend(window_days: int = 7) -> dict:
    """Compute week-over-week (or N-day-over-N-day) CPQP trend.

    Args:
        window_days: Window size in days. ``this_window`` covers
            ``-window_days .. now``; ``prior_window`` covers
            ``-2*window_days .. -window_days``.

    Returns:
        Dict with keys:
            - ``this_window``: average CPQP in the current window.
            - ``prior_window``: average CPQP in the prior window.
            - ``ratio``: ``this_window / prior_window`` (``< 1`` means
              the metric is improving, ``> 1`` means degrading,
              ``0.0`` if the prior window is empty).
    """
    conn = get_connection()
    this_row = conn.execute(
        """
        SELECT AVG(cpqp) AS avg_cpqp
        FROM cost_run_cpqp
        WHERE combined_score IS NOT NULL
          AND started_at >= datetime('now', ?)
        """,
        (f"-{window_days} days",),
    ).fetchone()

    prior_row = conn.execute(
        """
        SELECT AVG(cpqp) AS avg_cpqp
        FROM cost_run_cpqp
        WHERE combined_score IS NOT NULL
          AND started_at >= datetime('now', ?)
          AND started_at < datetime('now', ?)
        """,
        (f"-{window_days * 2} days", f"-{window_days} days"),
    ).fetchone()
    conn.close()

    this_avg = this_row["avg_cpqp"] if this_row and this_row["avg_cpqp"] else 0
    prior_avg = prior_row["avg_cpqp"] if prior_row and prior_row["avg_cpqp"] else 0
    ratio = round(this_avg / prior_avg, 4) if prior_avg > 0 else 0.0

    return {
        "this_window": round(this_avg, 4) if this_avg else 0,
        "prior_window": round(prior_avg, 4) if prior_avg else 0,
        "ratio": ratio,
    }


def get_spending_trend(days: Optional[int] = 30) -> list[dict]:
    """Return per-day spending aggregates for the trends CLI."""
    from cost_intel.report import report_by_day

    return report_by_day(days=days)
