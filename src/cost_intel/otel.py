"""OpenTelemetry span ingestion for multi-agent cost allocation."""

from typing import Optional

from cost_intel.record import record_run


def ingest_span(
    span_id: str,
    trace_id: str,
    agent_name: str,
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    parent_span_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> str:
    """Ingest an OpenTelemetry span as a cost run.

    Args:
        span_id: OTel span ID; used as the cost_runs.run_id so trace
            roll-ups can look spans up by their OTel identity.
        trace_id: OTel trace ID that groups spans into a single trace.
        agent_name: Human-readable agent label stored in cost_runs.label.
        model_id: Model identifier (e.g., 'openai/gpt-4o').
        input_tokens: Input token count for this span.
        output_tokens: Output token count for this span.
        parent_span_id: Parent span ID (None for the root span).
        latency_ms: Span duration in milliseconds.
        cache_read_tokens: Cache read token count.
        cache_write_tokens: Cache write token count.

    Returns:
        The run_id of the recorded span (equal to ``span_id``).
    """
    return record_run(
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        label=agent_name,
        run_type="agent_task",
        latency_ms=latency_ms,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        run_id=span_id,
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
    )
