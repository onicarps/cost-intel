"""Shared test fixtures for cost-intel test suite."""

import pytest


@pytest.fixture
def tmp_cost_intel_home(tmp_path, monkeypatch):
    """Set COST_INTEL_HOME to a temp dir for isolated tests.

    This prevents tests from reading/writing the real ~/.cost-intel/ directory.
    Yields the temp path.
    """
    cost_home = tmp_path / ".cost-intel"
    cost_home.mkdir()
    monkeypatch.setenv("COST_INTEL_HOME", str(cost_home))

    # Also patch the db module paths so they pick up the new home
    import cost_intel.config as config_mod

    config_mod.CONFIG_DIR = cost_home
    config_mod.CONFIG_PATH = cost_home / "config.yaml"
    config_mod._config_cache = None

    yield cost_home


@pytest.fixture
def tmp_db(tmp_cost_intel_home):
    """Initialize a fresh database in the temp cost-intel home.

    Yields an open sqlite3.Connection with WAL mode.
    """
    import sqlite3

    db_path = tmp_cost_intel_home / "cost-intel.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    yield conn
    conn.close()
