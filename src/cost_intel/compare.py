"""Model comparison — cost efficiency and CPQP delta across models."""

from typing import Optional

from cost_intel.db import get_connection


def compare_models(
    label: Optional[str] = None,
    models: Optional[list[str]] = None,
) -> list[dict]:
    """Compare cost and CPQP across models for the same task.

    Args:
        label: Optional task label to restrict the comparison to a
            specific workload.
        models: Optional list of model identifiers to restrict the
            comparison to a known set.

    Returns:
        List of dicts with per-model aggregates. Each dict includes:
            - ``model_id``, ``total_runs``
            - ``total_cost``, ``avg_cost_per_run``
            - ``total_input_tokens``, ``total_output_tokens``
            - ``avg_cpqp`` (average CPQP for runs that have a score)
            - ``delta_cpqp`` (avg_cpqp - min(avg_cpqp across models))
    """
    conn = get_connection()
    query = """
        SELECT
            cr.model_id,
            COUNT(DISTINCT cr.run_id) AS total_runs,
            COALESCE(SUM(crc.call_cost), 0) AS total_cost,
            COALESCE(AVG(crc.call_cost), 0) AS avg_cost_per_run,
            COALESCE(SUM(crc.input_tokens), 0) AS total_input_tokens,
            COALESCE(SUM(crc.output_tokens), 0) AS total_output_tokens,
            AVG(crp.cpqp) AS avg_cpqp
        FROM cost_runs cr
        JOIN cost_run_calls crc ON cr.run_id = crc.run_id
        LEFT JOIN cost_run_cpqp crp ON cr.run_id = crp.run_id
    """
    where_clauses: list[str] = []
    params: list = []
    if label:
        where_clauses.append("cr.label = ?")
        params.append(label)
    if models:
        placeholders = ",".join("?" for _ in models)
        where_clauses.append(f"cr.model_id IN ({placeholders})")
        params.extend(models)
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    query += " GROUP BY cr.model_id ORDER BY avg_cost_per_run ASC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = [dict(r) for r in rows]

    cpqp_values = [r["avg_cpqp"] for r in results if r.get("avg_cpqp") is not None]
    if cpqp_values:
        baseline = min(cpqp_values)
        for r in results:
            if r.get("avg_cpqp") is not None:
                r["delta_cpqp"] = round(r["avg_cpqp"] - baseline, 4)
            else:
                r["delta_cpqp"] = None
    else:
        for r in results:
            r["delta_cpqp"] = None

    return results
