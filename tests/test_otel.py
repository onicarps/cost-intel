"""Tests for OpenTelemetry span ingestion (Task 4.1) and trace cost (4.2)."""

from cost_intel.db import init_db
from cost_intel.otel import get_trace_cost, ingest_span
from cost_intel.pricing import set_manual_pricing
from cost_intel.record import get_run


def test_ingest_span_creates_run_with_span_id(tmp_cost_intel_home):
    init_db()
    run_id = ingest_span(
        span_id="span-1",
        trace_id="trace-1",
        agent_name="summarizer",
        model_id="openai/gpt-4o",
        input_tokens=100,
        output_tokens=50,
        parent_span_id=None,
    )
    assert run_id == "span-1"
    run = get_run("span-1")
    assert run is not None
    assert run["label"] == "summarizer"
    assert run["trace_id"] == "trace-1"
    assert run["span_id"] == "span-1"
    assert run["parent_span_id"] is None
    assert run["run_type"] == "agent_task"


def test_ingest_span_with_parent(tmp_cost_intel_home):
    init_db()
    ingest_span(
        span_id="span-child",
        trace_id="trace-1",
        agent_name="executor",
        model_id="openai/gpt-4o",
        input_tokens=200,
        output_tokens=100,
        parent_span_id="span-parent",
    )
    run = get_run("span-child")
    assert run["parent_span_id"] == "span-parent"
    assert run["trace_id"] == "trace-1"


def test_ingest_span_returns_run_id(tmp_cost_intel_home):
    init_db()
    result = ingest_span(
        span_id="span-42",
        trace_id="trace-99",
        agent_name="reviewer",
        model_id="openai/gpt-4o",
        input_tokens=50,
        output_tokens=25,
    )
    assert result == "span-42"


def test_trace_cost_filters_by_trace_id(tmp_cost_intel_home):
    """get_trace_cost must filter WHERE trace_id = ?, not return all rows."""
    init_db()
    set_manual_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    ingest_span("s1", "trace-A", "planner", "openai/gpt-4o", 200, 100)
    ingest_span("s2", "trace-A", "executor", "openai/gpt-4o", 500, 250)
    ingest_span("s3", "trace-B", "other", "openai/gpt-4o", 999, 999)

    cost = get_trace_cost("trace-A")
    assert cost["trace_id"] == "trace-A"
    assert cost["total_runs"] == 2
    agent_labels = {a["label"] for a in cost["agents"]}
    assert "other" not in agent_labels
    assert agent_labels == {"planner", "executor"}


def test_trace_cost_rolls_up_parent_spans(tmp_cost_intel_home):
    """Child span costs must roll up into parent totals."""
    init_db()
    set_manual_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    ingest_span(
        "root",
        "trace-1",
        "orchestrator",
        "openai/gpt-4o",
        100,
        50,
        parent_span_id=None,
    )
    ingest_span(
        "child-1",
        "trace-1",
        "planner",
        "openai/gpt-4o",
        200,
        100,
        parent_span_id="root",
    )
    ingest_span(
        "child-2",
        "trace-1",
        "executor",
        "openai/gpt-4o",
        300,
        150,
        parent_span_id="root",
    )

    cost = get_trace_cost("trace-1")
    assert cost["total_runs"] == 3
    orchestrator = next(a for a in cost["agents"] if a["label"] == "orchestrator")
    assert orchestrator["rolled_up_cost"] > orchestrator["own_cost"]
    assert orchestrator["depth"] == 0
    planner = next(a for a in cost["agents"] if a["label"] == "planner")
    assert planner["depth"] == 1
    expected_rolled = (
        orchestrator["own_cost"]
        + planner["own_cost"]
        + next(a for a in cost["agents"] if a["label"] == "executor")["own_cost"]
    )
    assert abs(orchestrator["rolled_up_cost"] - expected_rolled) < 1e-9


def test_trace_cost_with_cpqp(tmp_cost_intel_home):
    """CPQP must be computed at each level when quality scores exist."""
    from cost_intel.quality import import_score

    init_db()
    set_manual_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    ingest_span("s1", "trace-1", "agent-a", "openai/gpt-4o", 1000, 500)
    ingest_span("s2", "trace-1", "agent-b", "openai/gpt-4o", 200, 200)
    import_score("s1", score=0.5, source="test")
    import_score("s2", score=0.9, source="test")

    cost = get_trace_cost("trace-1")
    agent_a = next(a for a in cost["agents"] if a["label"] == "agent-a")
    agent_b = next(a for a in cost["agents"] if a["label"] == "agent-b")
    # agent-a: cost = 1*2.5 + 0.5*10 = 7.5; score=0.5 -> CPQP = 15.0
    # agent-b: cost = 0.2*2.5 + 0.2*10 = 2.5; score=0.9 -> CPQP ≈ 2.7778
    assert agent_a["cpqp"] == 15.0
    assert abs(agent_b["cpqp"] - 2.7778) < 0.01
