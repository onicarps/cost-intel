"""Database connection management and initialization.

Provides:
- get_connection(): raw connection with WAL + busy_timeout
- connect(): contextmanager with auto-commit/rollback
- init_db(): run migrations and return ready connection
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_DIR = Path.home() / ".cost-intel"
DB_DIR = Path(os.environ.get("COST_INTEL_HOME", str(DEFAULT_DB_DIR)))
DB_PATH = DB_DIR / "cost-intel.db"


def get_connection() -> sqlite3.Connection:
    """Get a raw SQLite connection with WAL mode and busy_timeout.

    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row.
    """
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def connect():
    """Context manager for database connections.

    Automatically commits on success, rolls back on exception,
    and always closes the connection.

    Yields:
        sqlite3.Connection with migrations applied.
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> sqlite3.Connection:
    """Initialize database — apply pending migrations and return connection.

    Returns:
        sqlite3.Connection ready for use with all current migrations applied.
    """
    from cost_intel.migration_runner import apply_pending_migrations

    conn = get_connection()
    apply_pending_migrations(conn)
    return conn
