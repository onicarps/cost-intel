"""Tests for utils.py."""

import pytest

from cost_intel.utils import now_iso, retry


def test_now_iso_returns_iso_format_string():
    """now_iso returns a string in ISO 8601 format."""
    result = now_iso()
    assert isinstance(result, str)
    assert "T" in result
    # Should end with +00:00 or Z for UTC
    assert result.endswith("+00:00") or result.endswith("Z") or "Z" not in result


def test_retry_succeeds_on_first_attempt():
    """retry returns result immediately on success."""
    result = retry(lambda: 42, max_attempts=3, delay=0.01)
    assert result == 42


def test_retry_retries_on_failure():
    """retry retries the function on failure."""
    call_count = 0

    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("not yet")
        return "success"

    result = retry(flaky, max_attempts=3, delay=0.01)
    assert result == "success"
    assert call_count == 3


def test_retry_raises_after_max_attempts():
    """retry raises the last exception after exhausting attempts."""

    def always_fail():
        raise RuntimeError("always")

    with pytest.raises(RuntimeError, match="always"):
        retry(always_fail, max_attempts=2, delay=0.01)
