"""Tests for budget enforcement guard."""

from cost_intel.guard import check_guard


def test_guard_allows_when_under_budget(tmp_cost_intel_home):
    from cost_intel.budget import set_budget
    from cost_intel.db import init_db

    init_db()
    set_budget(monthly=1000, alert_threshold=80)
    allowed, msg = check_guard()
    assert allowed is True


def test_guard_blocks_when_budget_exceeded(tmp_cost_intel_home):
    from cost_intel.budget import set_budget
    from cost_intel.db import init_db

    init_db()
    set_budget(monthly=0, alert_threshold=0)
    allowed, msg = check_guard()
    assert allowed is False
    assert "budget" in msg.lower()


def test_guard_no_budget_set(tmp_cost_intel_home):
    from cost_intel.db import init_db

    init_db()
    allowed, msg = check_guard()
    assert allowed is True


def test_guard_with_custom_threshold(tmp_cost_intel_home):
    from cost_intel.budget import set_budget
    from cost_intel.db import init_db

    init_db()
    set_budget(monthly=100, alert_threshold=50)
    allowed, msg = check_guard(threshold_override=0.5)
    assert allowed is True
