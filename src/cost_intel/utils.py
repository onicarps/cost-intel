"""Shared utilities — retry, now_iso.

NOTE: `parse_window` lives in `src/cost_intel/duration.py` (Task 3.0) — the
canonical location with tests in `tests/test_duration.py`. Do NOT duplicate
it here. Import from `cost_intel.duration` instead.
"""

import time
from datetime import datetime, timezone
from typing import Any, Callable


def now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def retry(func: Callable[[], Any], max_attempts: int = 3, delay: float = 1.0) -> Any:
    """Retry a function with exponential backoff.

    Args:
        func: The function to call.
        max_attempts: Maximum number of attempts.
        delay: Initial delay in seconds (doubles each retry).

    Returns:
        The result of the successful function call.

    Raises:
        The last exception if all attempts fail.
    """
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            last_err = e
            if attempt < max_attempts - 1:
                time.sleep(delay * (2**attempt))
    raise last_err  # type: ignore[misc]
