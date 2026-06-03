"""Budget enforcement — hard-stop guard for API calls."""

from typing import Optional

from cost_intel.budget import get_budget_status


def check_guard(threshold_override: Optional[float] = None) -> tuple[bool, str]:
    """Check if the monthly budget allows new API calls.

    Args:
        threshold_override: If set, use this threshold (0.0-1.0) instead
            of the configured alert_threshold.

    Returns:
        (allowed, message) — allowed=False means budget exceeded.
    """
    status = get_budget_status()

    if not status["budget_set"]:
        return True, "No budget configured — guard allows"

    effective_threshold = (
        threshold_override
        if threshold_override is not None
        else status["alert_threshold"]
    )
    percent_used = status["percent_used"]

    if percent_used >= effective_threshold:
        return (
            False,
            f"Budget exceeded: ${status['spent']:.2f} spent "
            f"of ${status['monthly']:.2f} monthly budget "
            f"({percent_used}% >= {effective_threshold}% threshold). "
            f"API call blocked.",
        )

    return (
        True,
        f"Budget OK: ${status['spent']:.2f} spent "
        f"of ${status['monthly']:.2f} ({percent_used}%)",
    )
