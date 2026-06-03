"""Numbered SQL migration runner with schema_version tracking."""

import sqlite3
from pathlib import Path
from typing import Optional

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _get_migration_files() -> list[tuple[int, Path]]:
    """Get sorted list of (version, path) for all migration SQL files."""
    if not _MIGRATIONS_DIR.exists():
        return []
    files: list[tuple[int, Path]] = []
    for f in _MIGRATIONS_DIR.glob("*.sql"):
        try:
            ver = int(f.stem.split("_")[0])
            files.append((ver, f))
        except (ValueError, IndexError):
            continue
    return sorted(files, key=lambda x: x[0])


def get_current_version(
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Get the current schema version from the database.

    Args:
        conn: Optional connection. If None, creates a new one.

    Returns:
        Current version number (0 if schema_version table doesn't exist).
    """
    should_close = conn is None
    if conn is None:
        from cost_intel.db import get_connection

        conn = get_connection()

    try:
        result = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='schema_version'"
        ).fetchone()
        if result is None:
            return 0

        row = conn.execute("SELECT MAX(version) as ver FROM schema_version").fetchone()
        return row["ver"] if row and row["ver"] is not None else 0
    finally:
        if should_close:
            conn.close()


def apply_pending_migrations(
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """Apply all pending migration SQL files in order.

    Each migration is executed in a transaction. The version number
    is recorded in schema_version after successful execution.

    Args:
        conn: Optional connection. If None, creates a new one.

    Returns:
        Number of migrations applied.
    """
    should_close = conn is None
    if conn is None:
        from cost_intel.db import get_connection

        conn = get_connection()

    try:
        current = get_current_version(conn)
        migration_files = _get_migration_files()
        applied = 0

        for version, path in migration_files:
            if version <= current:
                continue

            sql = path.read_text()
            # Execute the migration SQL
            conn.executescript(sql)
            # Record the version
            conn.execute(
                "INSERT OR REPLACE INTO schema_version (version, applied_at) "
                "VALUES (?, datetime('now'))",
                (version,),
            )
            conn.commit()
            applied += 1

        return applied
    finally:
        if should_close:
            conn.close()
