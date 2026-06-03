"""Cost run recording with cache tokens, historical pricing, raw_response."""

import uuid
from typing import Optional

from cost_intel.db import get_connection
from cost_intel.pricing import get_pricing
from cost_intel.utils import now_iso


def _compute_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    as_of_date: Optional[str] = None,
) -> float:
    """Compute cost for a run based on model pricing.

    Args:
        model_id: Model identifier.
        input_tokens: Input token count.
        output_tokens: Output token count.
        cache_read_tokens: Cache read token count.
        cache_write_tokens: Cache write token count.
        as_of_date: Optional date for historical pricing.

    Returns:
        Computed cost in USD, or 0.0 if no pricing found.
    """
    pricing = get_pricing(model_id, as_of_date=as_of_date)
    if not pricing:
        return 0.0
    ic = (input_tokens / 1_000_000) * (pricing["input_price_per_1k_tokens"] or 0)
    oc = (output_tokens / 1_000_000) * (pricing["output_price_per_1k_tokens"] or 0)
    crc = (cache_read_tokens / 1_000_000) * (
        pricing["cache_read_price_per_1k_tokens"] or 0
    )
    cwc = (cache_write_tokens / 1_000_000) * (
        pricing["cache_write_price_per_1k_tokens"] or 0
    )
    return round(ic + oc + crc + cwc, 6)


def record_run(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    label: Optional[str] = None,
    run_type: str = "api_call",
    provider: Optional[str] = None,
    latency_ms: Optional[int] = None,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    raw_response: Optional[str] = None,
    as_of_date: Optional[str] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    parent_span_id: Optional[str] = None,
    run_id: Optional[str] = None,
) -> str:
    """Record a cost run and its API call details.

    Args:
        model_id: Model identifier (e.g., 'openai/gpt-4o').
        input_tokens: Input token count.
        output_tokens: Output token count.
        label: Human-readable label for the run.
        run_type: Type of run ('api_call', 'agent_task', 'workflow').
        provider: Provider name (auto-detected from model_id if None).
        latency_ms: Request latency in milliseconds.
        cache_read_tokens: Cache read token count.
        cache_write_tokens: Cache write token count.
        raw_response: Optional response body (truncated to 4KB).
        as_of_date: Date for historical pricing lookup.
        trace_id: OpenTelemetry trace ID for cross-span correlation.
        span_id: OpenTelemetry span ID for this run.
        parent_span_id: Parent span ID for trace hierarchy.
        run_id: Optional explicit run ID (auto-generated if None).

    Returns:
        The run_id of the recorded run.
    """
    rid = run_id or str(uuid.uuid4())
    now = now_iso()
    cost = _compute_cost(
        model_id,
        input_tokens,
        output_tokens,
        cache_read_tokens,
        cache_write_tokens,
        as_of_date,
    )
    prov = provider or (model_id.split("/")[0] if "/" in model_id else "unknown")
    if raw_response and len(raw_response) > 4096:
        raw_response = raw_response[:4096]

    conn = get_connection()
    conn.execute(
        "INSERT INTO cost_runs "
        "(run_id, run_type, label, model_id, started_at, "
        "finished_at, status, trace_id, span_id, parent_span_id) "
        "VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?)",
        (
            rid,
            run_type,
            label,
            model_id,
            now,
            now,
            trace_id,
            span_id,
            parent_span_id,
        ),
    )
    conn.execute(
        "INSERT INTO cost_run_calls "
        "(run_id, sequence, provider, model, input_tokens, "
        "output_tokens, cache_read_tokens, cache_write_tokens, "
        "call_cost, latency_ms, raw_response) "
        "VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rid,
            prov,
            model_id,
            input_tokens,
            output_tokens,
            cache_read_tokens,
            cache_write_tokens,
            cost,
            latency_ms,
            raw_response,
        ),
    )
    conn.commit()
    conn.close()
    return rid


def get_run(run_id: str) -> Optional[dict]:
    """Get a run by its ID.

    Args:
        run_id: The run identifier.

    Returns:
        Run dict or None if not found.
    """
    conn = get_connection()
    row = conn.execute("SELECT * FROM cost_runs WHERE run_id = ?", (run_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_run_calls(run_id: str) -> list[dict]:
    """Get all API calls for a run.

    Args:
        run_id: The run identifier.

    Returns:
        List of call dicts.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM cost_run_calls WHERE run_id = ? ORDER BY sequence",
        (run_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
