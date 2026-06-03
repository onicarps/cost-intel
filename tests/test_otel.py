"""Tests for OpenTelemetry span ingestion (Task 4.1)."""

from cost_intel.db import init_db
from cost_intel.otel import ingest_span
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
