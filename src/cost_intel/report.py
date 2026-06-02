"""Cost reporting — aggregate views with time-window filtering.

All report functions accept an optional `days` parameter to filter
to the last N days. Default is None (all time).
"""

from typing import Optional

from cost_intel.db import connect


def _days_filter(days: Optional[int]) -> tuple[str, list]:
    """Build SQL WHERE clause and params for time-window filtering.

    Args:
        days: Number of days to look back, or None for all time.

    Returns:
        Tuple of (where_clause, params_list).
    """
    if days is not None:
        return (
            " WHERE cr.started_at >= datetime('now', ?)",
            [f"-{days} days"],
        )
    return ("", [])


def report_summary(days: Optional[int] = None) -> dict:
    """Get aggregate cost summary.

    Args:
        days: Optional time window in days.

    Returns:
        Dict with total_runs, total_cost, avg_cost_per_run,
        total_input_tokens, total_output_tokens.
    """
    where, params = _days_filter(days)
    with connect() as conn:
        row = conn.execute(
            f"SELECT "
            f"COUNT(DISTINCT cr.run_id) as total_runs, "
            f"COALESCE(SUM(crc.call_cost), 0) as total_cost, "
            f"COALESCE(AVG(crc.call_cost), 0) as avg_cost_per_run, "
            f"COALESCE(SUM(crc.input_tokens), 0) as total_input_tokens, "
            f"COALESCE(SUM(crc.output_tokens), 0) as total_output_tokens "
            f"FROM cost_runs cr "
            f"LEFT JOIN cost_run_calls crc ON cr.run_id = crc.run_id"
            f"{where}",
            params,
        ).fetchone()
    return dict(row) if row else {}


def report_by_model(days: Optional[int] = None) -> list[dict]:
    """Get cost report grouped by model.

    Args:
        days: Optional time window in days.

    Returns:
        List of dicts with model_id, run_count, total_cost,
        avg_cost, total_input_tokens, total_output_tokens.
    """
    where, params = _days_filter(days)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT "
            f"cr.model_id, "
            f"COUNT(DISTINCT cr.run_id) as run_count, "
            f"COALESCE(SUM(crc.call_cost), 0) as total_cost, "
            f"COALESCE(AVG(crc.call_cost), 0) as avg_cost, "
            f"COALESCE(SUM(crc.input_tokens), 0) as total_input_tokens, "
            f"COALESCE(SUM(crc.output_tokens), 0) as total_output_tokens "
            f"FROM cost_runs cr "
            f"LEFT JOIN cost_run_calls crc ON cr.run_id = crc.run_id"
            f"{where} "
            f"GROUP BY cr.model_id "
            f"ORDER BY total_cost DESC",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def report_by_label(days: Optional[int] = None) -> list[dict]:
    """Get cost report grouped by label.

    Args:
        days: Optional time window in days.

    Returns:
        List of dicts with label, run_count, total_cost, avg_cost.
    """
    where, params = _days_filter(days)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT "
            f"cr.label, "
            f"COUNT(DISTINCT cr.run_id) as run_count, "
            f"COALESCE(SUM(crc.call_cost), 0) as total_cost, "
            f"COALESCE(AVG(crc.call_cost), 0) as avg_cost "
            f"FROM cost_runs cr "
            f"LEFT JOIN cost_run_calls crc ON cr.run_id = crc.run_id"
            f"{where} "
            f"GROUP BY cr.label "
            f"ORDER BY total_cost DESC",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def report_by_day(days: Optional[int] = None) -> list[dict]:
    """Get cost report grouped by day.

    Args:
        days: Optional time window in days.

    Returns:
        List of dicts with date, run_count, total_cost, avg_cost.
    """
    where, params = _days_filter(days)
    with connect() as conn:
        rows = conn.execute(
            f"SELECT "
            f"date(cr.started_at) as date, "
            f"COUNT(DISTINCT cr.run_id) as run_count, "
            f"COALESCE(SUM(crc.call_cost), 0) as total_cost, "
            f"COALESCE(AVG(crc.call_cost), 0) as avg_cost "
            f"FROM cost_runs cr "
            f"LEFT JOIN cost_run_calls crc ON cr.run_id = crc.run_id"
            f"{where} "
            f"GROUP BY date(cr.started_at) "
            f"ORDER BY date DESC",
            params,
        ).fetchall()
    return [dict(r) for r in rows]
