"""Budget management — set, status, and alert tracking."""

from cost_intel.db import connect


def set_budget(monthly: float, alert_threshold: int = 80) -> None:
    """Set the monthly budget and alert threshold.

    Args:
        monthly: Monthly budget in USD.
        alert_threshold: Percentage at which to trigger alerts (0-100).
    """
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("monthly_budget", str(monthly)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("alert_threshold", str(alert_threshold)),
        )


def get_budget_status() -> dict:
    """Get current budget status including spending.

    Returns:
        Dict with budget_set, monthly, alert_threshold, spent,
        remaining, percent_used.
    """
    with connect() as conn:
        budget_row = conn.execute(
            "SELECT value FROM config WHERE key = ?",
            ("monthly_budget",),
        ).fetchone()
        threshold_row = conn.execute(
            "SELECT value FROM config WHERE key = ?",
            ("alert_threshold",),
        ).fetchone()

    if budget_row is None:
        return {
            "budget_set": False,
            "monthly": None,
            "alert_threshold": None,
            "spent": 0.0,
            "remaining": None,
            "percent_used": 0.0,
        }

    monthly = float(budget_row["value"])
    alert_threshold = int(threshold_row["value"]) if threshold_row else 80

    # Calculate current month spending
    with connect() as conn:
        spent_row = conn.execute(
            "SELECT COALESCE(SUM(call_cost), 0) as spent "
            "FROM cost_run_calls crc "
            "JOIN cost_runs cr ON crc.run_id = cr.run_id "
            "WHERE cr.started_at >= date('now', 'start of month')"
        ).fetchone()
    spent = float(spent_row["spent"]) if spent_row else 0.0

    remaining = max(0.0, monthly - spent)
    percent_used = (spent / monthly * 100) if monthly > 0 else 0.0

    return {
        "budget_set": True,
        "monthly": monthly,
        "alert_threshold": alert_threshold,
        "spent": round(spent, 2),
        "remaining": round(remaining, 2),
        "percent_used": round(percent_used, 1),
    }
