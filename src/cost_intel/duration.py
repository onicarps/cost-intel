"""Duration parser — canonical location for parse_window.

All --last/--days/--window CLI flags import from here.
Do NOT duplicate this function in utils.py or inline.
"""

import math


def parse_window(value: str) -> int:
    """Parse a duration string into days.

    Supported formats:
        - '7d'  → 7 (days)
        - '24h' → 1 (24 hours = 1 day, rounded up)
        - '1w'  → 7 (weeks)
        - '7'   → 7 (bare integer treated as days)

    Args:
        value: Duration string (e.g., '7d', '30d', '24h', '1w').

    Returns:
        Number of days as integer (minimum 1).

    Raises:
        ValueError: If the string cannot be parsed.
    """
    value = value.strip().lower()
    if not value:
        raise ValueError("Empty duration string")

    if value.endswith("w"):
        return int(value[:-1]) * 7

    if value.endswith("d"):
        return int(value[:-1])

    if value.endswith("h"):
        hours = int(value[:-1])
        return max(1, math.ceil(hours / 24))

    # Bare integer — treat as days
    return int(value)
