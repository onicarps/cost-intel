"""Optimization suggestions — model routing, waste index, target CPQP."""

from typing import Optional

from cost_intel.db import get_connection


def suggest_model_routing(
    label: Optional[str] = None,
    min_runs: int = 1,
) -> list[dict]:
    """Suggest cheaper models for the same task from historical data.

    Args:
        label: Optional task label to restrict suggestions.
        min_runs: Minimum number of runs a model must have to qualify.
            Defaults to ``1``. Increase for more statistical confidence.

    Returns:
        Per-model aggregates sorted by ``avg_cost_per_run`` ascending.
    """
    conn = get_connection()
    query = """
        SELECT
            cr.model_id,
            COUNT(*) AS total_runs,
            AVG(crc.call_cost) AS avg_cost_per_run,
            MIN(crc.call_cost) AS min_cost,
            MAX(crc.call_cost) AS max_cost
        FROM cost_runs cr
        JOIN cost_run_calls crc ON cr.run_id = crc.run_id
    """
    params: list = []
    if label:
        query += " WHERE cr.label = ?"
        params.append(label)
    query += (
        " GROUP BY cr.model_id HAVING total_runs >= ? ORDER BY avg_cost_per_run ASC"
    )
    params.append(min_runs)
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_waste_index(
    days: Optional[int] = None,
    target_cpqp: Optional[float] = None,
) -> dict:
    """Return waste-index summary: share of spend on inefficient runs.

    By default, runs rated ``D`` or ``F`` (percentile-based) are counted
    as waste. When ``target_cpqp`` is provided, runs with CPQP above
    the target are counted instead.

    Args:
        days: Optional time window in days.
        target_cpqp: Optional explicit CPQP threshold. When set, waste
            is defined as ``cpqp > target_cpqp`` instead of D/F rating.

    Returns:
        Dict with ``total_spend``, ``waste_spend``, ``waste_index``.
    """
    conn = get_connection()

    total_where = ""
    total_params: list = []
    if days is not None:
        total_where = (
            " WHERE crc.run_id IN ("
            "SELECT run_id FROM cost_runs "
            "WHERE started_at >= datetime('now', ?))"
        )
        total_params.append(f"-{days} days")

    total_row = conn.execute(
        f"SELECT COALESCE(SUM(crc.call_cost), 0) AS total "
        f"FROM cost_run_calls crc{total_where}",
        total_params,
    ).fetchone()
    total = total_row["total"] if total_row else 0

    if target_cpqp is not None:
        waste_query = (
            "SELECT COALESCE(SUM(total_cost), 0) AS waste_total "
            "FROM cost_run_cpqp "
            "WHERE combined_score IS NOT NULL AND cpqp > ?"
        )
        waste_params: list = [target_cpqp]
    else:
        waste_query = (
            "SELECT COALESCE(SUM(total_cost), 0) AS waste_total "
            "FROM cost_run_cpqp WHERE rating IN ('D', 'F')"
        )
        waste_params = []

    if days is not None:
        waste_query += " AND started_at >= datetime('now', ?)"
        waste_params.append(f"-{days} days")

    waste_row = conn.execute(waste_query, waste_params).fetchone()
    conn.close()

    waste = waste_row["waste_total"] if waste_row else 0
    return {
        "total_spend": total,
        "waste_spend": waste,
        "waste_index": round(waste / total, 4) if total > 0 else 0.0,
    }


def get_runs_above_target_cpqp(target_cpqp: float) -> list[dict]:
    """Return runs whose CPQP exceeds the given target."""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT *
        FROM cost_run_cpqp
        WHERE combined_score IS NOT NULL
          AND cpqp > ?
        ORDER BY cpqp DESC
        """,
        (target_cpqp,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
