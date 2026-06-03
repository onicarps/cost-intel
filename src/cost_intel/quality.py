"""Quality score import, CPQP calculation, and waste detection.

Stores quality scores in the `quality_scores` table and exposes
percentile-based CPQP results via the `cost_run_cpqp` view.
"""

import csv
import json
from typing import Optional

from cost_intel.db import get_connection


def compute_combined_score(
    dimensions: dict[str, float],
    weights: Optional[dict[str, float]] = None,
) -> float:
    """Compute weighted combined score from multiple eval dimensions.

    Args:
        dimensions: Mapping of dimension name → score (0.0-1.0).
        weights: Mapping of dimension name → weight. If None, equal
            weights are used. Weights are normalized to sum to 1.0.

    Returns:
        Combined score in [0.0, 1.0].
    """
    if not dimensions:
        return 0.0

    if weights is None:
        n = len(dimensions)
        weights = {k: 1.0 / n for k in dimensions}

    total_w = sum(weights.get(k, 0.0) for k in dimensions)
    if total_w <= 0:
        return 0.0

    combined = sum(dimensions[k] * (weights.get(k, 0.0) / total_w) for k in dimensions)
    return max(0.0, min(1.0, combined))


def import_score(
    run_id: str,
    score: Optional[float],
    source: str,
    source_run_id: Optional[str] = None,
    eval_dimensions: Optional[dict] = None,
    eval_weights: Optional[dict] = None,
    notes: Optional[str] = None,
) -> None:
    """Import a quality score for a cost run.

    If `eval_dimensions` is supplied and `score` is None, the combined
    score is auto-computed using `compute_combined_score()`.

    Args:
        run_id: Cost run identifier.
        score: Combined score in [0.0, 1.0]. Out-of-range values are
            clamped.
        source: Provenance label (e.g. ``"csv"``, ``"eval_harness"``).
        source_run_id: Optional identifier from the upstream source.
        eval_dimensions: Optional per-dimension scores.
        eval_weights: Optional per-dimension weights.
        notes: Optional free-form notes.
    """
    if score is None and eval_dimensions:
        score = compute_combined_score(eval_dimensions, eval_weights)
    elif score is None:
        score = 0.0

    score = max(0.0, min(1.0, float(score)))

    conn = get_connection()
    conn.execute(
        """
        INSERT INTO quality_scores
            (run_id, source, source_run_id, combined_score,
             eval_dimensions, eval_weights, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            source,
            source_run_id,
            score,
            json.dumps(eval_dimensions) if eval_dimensions else None,
            json.dumps(eval_weights) if eval_weights else None,
            notes,
        ),
    )
    conn.commit()
    conn.close()


def import_scores_csv(
    file_path: str,
    run_id_col: str = "run_id",
    score_col: str = "score",
    source: str = "csv",
    mapping: Optional[dict] = None,
) -> int:
    """Import quality scores from a CSV file.

    Args:
        file_path: Path to the CSV file.
        run_id_col: Column name for the run identifier.
        score_col: Column name for the score value.
        source: Provenance label written to ``quality_scores.source``.
        mapping: Optional column-name mapping. Keys are the canonical
            names (``"run_id"``, ``"score"``); values are the actual
            CSV column names. Example::

                {"run_id": "id", "score": "quality"}

    Returns:
        Count of rows successfully imported.
    """
    if mapping:
        run_id_col = mapping.get("run_id", run_id_col)
        score_col = mapping.get("score", score_col)

    count = 0
    with open(file_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            run_id = row.get(run_id_col, "")
            try:
                score = float(row.get(score_col, 0))
            except (ValueError, TypeError):
                continue
            if not run_id:
                continue
            import_score(run_id=run_id, score=score, source=source)
            count += 1
    return count


def get_cpqp(run_id: str) -> Optional[dict]:
    """Return the CPQP view row for a single run, or None."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM cost_run_cpqp WHERE run_id = ?", (run_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_cpqp(
    days: Optional[int] = None,
    limit: Optional[int] = None,
    min_rating: Optional[str] = None,
) -> list[dict]:
    """Return CPQP rows for runs that have quality scores.

    Args:
        days: Optional time window — keep only runs whose ``started_at``
            is within the last N days.
        limit: Optional maximum number of rows.
        min_rating: Optional letter rating threshold. ``"D"`` returns
            D and F rows only.
    """
    conn = get_connection()
    query = "SELECT * FROM cost_run_cpqp WHERE combined_score IS NOT NULL"
    params: list = []

    if days is not None:
        query += " AND started_at >= datetime('now', ?)"
        params.append(f"-{days} days")

    if min_rating:
        rating_order = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
        threshold = rating_order.get(min_rating, 4)
        allowed = [r for r, v in rating_order.items() if v >= threshold]
        placeholders = ",".join("?" for _ in allowed)
        query += f" AND rating IN ({placeholders})"
        params.extend(allowed)

    query += " ORDER BY cpqp DESC"
    if limit:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_waste_runs(days: Optional[int] = None) -> list[dict]:
    """Return runs with a D or F rating (top-25% CPQP).

    Uses the percentile-based rating from the ``cost_run_cpqp`` view,
    so the threshold scales with the dataset rather than relying on a
    hard-coded dollar value.
    """
    conn = get_connection()
    query = "SELECT * FROM cost_run_cpqp WHERE rating IN ('D', 'F')"
    params: list = []
    if days is not None:
        query += " AND started_at >= datetime('now', ?)"
        params.append(f"-{days} days")
    query += " ORDER BY cpqp DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]
