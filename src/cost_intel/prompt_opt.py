"""Prompt optimization suggestions — identify high-cost label patterns."""

from cost_intel.db import connect


def analyze_prompt_patterns(top_n: int = 10) -> list[dict]:
    """Analyze top N highest-cost label prefixes.

    Groups runs by label prefix (the first word before ``-`` or ``_``)
    and computes aggregate cost statistics. Only includes prefixes with
    at least 2 runs. Returns rows sorted by ``avg_cost`` descending.

    Args:
        top_n: Maximum number of prefix rows to return.

    Returns:
        List of dicts with keys ``label_prefix``, ``total_runs``,
        ``total_cost``, ``avg_cost``, ``avg_input_tokens``,
        ``avg_output_tokens``, ``min_cost``, ``max_cost``.
    """
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                CASE
                    WHEN cr.label LIKE '%-%' AND
                         (INSTR(cr.label, '_') = 0 OR
                          INSTR(cr.label, '-') < INSTR(cr.label, '_'))
                        THEN SUBSTR(cr.label, 1, INSTR(cr.label, '-') - 1)
                    WHEN cr.label LIKE '%_%'
                        THEN SUBSTR(cr.label, 1, INSTR(cr.label, '_') - 1)
                    ELSE COALESCE(cr.label, '(unlabeled)')
                END AS label_prefix,
                COUNT(*) AS total_runs,
                SUM(crc.call_cost) AS total_cost,
                AVG(crc.call_cost) AS avg_cost,
                AVG(crc.input_tokens) AS avg_input_tokens,
                AVG(crc.output_tokens) AS avg_output_tokens,
                MIN(crc.call_cost) AS min_cost,
                MAX(crc.call_cost) AS max_cost
            FROM cost_runs cr
            JOIN cost_run_calls crc ON cr.run_id = crc.run_id
            GROUP BY label_prefix
            HAVING total_runs >= 2
            ORDER BY avg_cost DESC
            LIMIT ?
            """,
            (top_n,),
        ).fetchall()
        return [dict(r) for r in rows]


def suggest_trimming(threshold_tokens: int = 3000) -> list[dict]:
    """Suggest prompt trimming for high-input-token labels.

    Finds labels where the average input token count exceeds the
    threshold (minimum 2 runs) and emits an actionable suggestion
    string for each.

    Args:
        threshold_tokens: Minimum average input tokens for a label to
            appear in the suggestions.

    Returns:
        List of dicts with keys ``label``, ``runs``, ``avg_input_tokens``,
        ``avg_cost``, ``suggestion``.
    """
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                cr.label AS label,
                COUNT(*) AS runs,
                AVG(crc.input_tokens) AS avg_input_tokens,
                AVG(crc.call_cost) AS avg_cost,
                AVG(crc.output_tokens) AS avg_output_tokens
            FROM cost_runs cr
            JOIN cost_run_calls crc ON cr.run_id = crc.run_id
            WHERE cr.label IS NOT NULL
            GROUP BY cr.label
            HAVING runs >= 2 AND avg_input_tokens > ?
            ORDER BY avg_cost DESC
            """,
            (threshold_tokens,),
        ).fetchall()

    suggestions = []
    for row in rows:
        avg_in = row["avg_input_tokens"]
        suggestions.append(
            {
                "label": row["label"],
                "runs": row["runs"],
                "avg_input_tokens": avg_in,
                "avg_cost": row["avg_cost"],
                "suggestion": (
                    f"Label '{row['label']}' averages {int(avg_in)} input tokens "
                    f"(${row['avg_cost']:.4f}/run). Consider: "
                    f"(1) trim the system prompt, "
                    f"(2) reduce few-shot examples, "
                    f"(3) cache repeated context, "
                    f"(4) split into smaller sub-tasks, "
                    f"(5) route to a cheaper model."
                ),
            }
        )
    return suggestions
