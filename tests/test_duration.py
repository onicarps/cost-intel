"""Tests for duration.py — parse_window helper."""

import pytest

from cost_intel.duration import parse_window


def test_parse_window_days_suffix():
    """parse_window('7d') returns 7."""
    assert parse_window("7d") == 7


def test_parse_window_30_days():
    """parse_window('30d') returns 30."""
    assert parse_window("30d") == 30


def test_parse_window_hours_suffix():
    """parse_window('24h') returns 1 (24 hours = 1 day)."""
    assert parse_window("24h") == 1


def test_parse_window_hours_rounds_up():
    """parse_window('12h') returns 1 (minimum 1 day)."""
    assert parse_window("12h") == 1


def test_parse_window_hours_multiple_days():
    """parse_window('72h') returns 3."""
    assert parse_window("72h") == 3


def test_parse_window_week_suffix():
    """parse_window('1w') returns 7."""
    assert parse_window("1w") == 7


def test_parse_window_2_weeks():
    """parse_window('2w') returns 14."""
    assert parse_window("2w") == 14


def test_parse_window_bare_integer():
    """parse_window('7') returns 7 (bare integer treated as days)."""
    assert parse_window("7") == 7


def test_parse_window_strips_whitespace():
    """parse_window handles leading/trailing whitespace."""
    assert parse_window("  7d  ") == 7


def test_parse_window_case_insensitive():
    """parse_window is case-insensitive."""
    assert parse_window("7D") == 7


def test_parse_window_invalid_raises():
    """parse_window raises ValueError for unparseable input."""
    with pytest.raises(ValueError):
        parse_window("abc")
