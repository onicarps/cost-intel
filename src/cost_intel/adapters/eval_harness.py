"""Eval Harness adapter — import quality scores from a SQLite database."""

import sqlite3

from cost_intel.quality import import_score


def import_from_db(
    db_path: str,
    source: str = "eval_harness",
    run_id_column: str = "run_id",
    score_column: str = "score",
) -> int:
    """Read scores from an Eval Harness SQLite DB and import them.

    The adapter tries the ``results`` table first, then ``eval_results``
    as a fallback. Returns ``0`` if neither table exists.

    Args:
        db_path: Filesystem path to the Eval Harness database.
        source: Provenance label written to ``quality_scores.source``.
        run_id_column: Name of the column holding the run id.
        score_column: Name of the column holding the score.

    Returns:
        Count of imported rows.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows: list = []
    try:
        try:
            rows = conn.execute(
                f"SELECT {run_id_column}, {score_column} FROM results"
            ).fetchall()
        except sqlite3.OperationalError:
            try:
                rows = conn.execute(
                    f"SELECT {run_id_column}, {score_column} FROM eval_results"
                ).fetchall()
            except sqlite3.OperationalError:
                return 0
    finally:
        conn.close()

    count = 0
    for row in rows:
        run_id = str(row[run_id_column]) if row[run_id_column] else None
        score = float(row[score_column]) if row[score_column] is not None else None
        if run_id and score is not None:
            import_score(run_id=run_id, score=score, source=source)
            count += 1
    return count
