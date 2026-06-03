"""CI/CD cost gates — fail builds when cost thresholds are exceeded."""

from typing import Optional

from cost_intel.db import get_connection
from cost_intel.optimize import get_waste_index


def check_gate(
    max_avg_cpqp: Optional[float] = None,
    max_waste_index: Optional[float] = None,
    budget_check: bool = False,
    window_days: int = 7,
) -> tuple[bool, str]:
    """Check cost gates. Returns ``(passed, message)``.

    Args:
        max_avg_cpqp: Optional maximum average cost-per-quality-point over the
            window. When set but zero runs have quality scores in the window,
            the gate fails with an informative message rather than silently
            passing.
        max_waste_index: Optional maximum waste-index (share of spend on
            D/F rated runs) in ``[0.0, 1.0]``.
        budget_check: When True, fails when the monthly budget alert
            threshold is reached.
        window_days: Window size in days for the CPQP check.

    Returns:
        Tuple of ``(passed, message)``. ``passed`` is True when every
        configured check passes; ``message`` is a human-readable summary.
    """
    if max_avg_cpqp is not None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS scored_runs, AVG(cpqp) AS avg_cpqp
                FROM cost_run_cpqp
                WHERE combined_score IS NOT NULL
                  AND started_at >= datetime('now', ?)
                """,
                (f"-{window_days} days",),
            ).fetchone()

        scored_runs = row["scored_runs"] if row else 0
        avg_cpqp = row["avg_cpqp"] if row and row["avg_cpqp"] is not None else None

        if scored_runs == 0 or avg_cpqp is None:
            return (
                False,
                "No quality score data in window — cannot evaluate CPQP gate",
            )

        if avg_cpqp > max_avg_cpqp:
            return (
                False,
                f"Average CPQP ${avg_cpqp:.4f} exceeds threshold ${max_avg_cpqp:.4f}",
            )

    if max_waste_index is not None:
        wi = get_waste_index(days=window_days)
        if wi["waste_index"] > max_waste_index:
            return (
                False,
                f"Waste index {wi['waste_index']:.1%} exceeds threshold "
                f"{max_waste_index:.1%}",
            )

    if budget_check:
        from cost_intel.budget import get_budget_status

        status = get_budget_status()
        if status["budget_set"]:
            percent_used = status["percent_used"]
            threshold = status["alert_threshold"]
            if percent_used >= threshold:
                return (
                    False,
                    f"Budget {percent_used:.1f}% used (threshold {threshold}%)",
                )

    return True, "All gates passed"
