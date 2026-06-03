"""OpenTelemetry span ingestion for multi-agent cost allocation."""

from typing import Optional

from cost_intel.db import get_connection
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


def get_trace_cost(trace_id: str) -> dict:
    """Get cost breakdown for a trace with span-tree roll-up and CPQP.

    Filters cost runs by ``trace_id`` and aggregates per-span costs from
    ``cost_run_calls``. Walks the ``parent_span_id`` graph to roll child
    costs up into each ancestor's ``rolled_up_cost``. CPQP is computed
    per span when a matching quality score exists.

    Args:
        trace_id: OpenTelemetry trace ID to summarise.

    Returns:
        A dict with keys:
            - ``trace_id``: echo of the input.
            - ``agents``: list of per-span dicts (``run_id``, ``label``,
              ``model_id``, ``parent_span_id``, ``span_id``, ``own_cost``,
              ``rolled_up_cost``, ``input_tokens``, ``output_tokens``,
              ``combined_score``, ``cpqp``, ``depth``).
            - ``total_runs``: count of spans in the trace.
            - ``total_cost``: sum of ``own_cost`` across spans.
            - ``total_input_tokens`` / ``total_output_tokens``: token sums.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                cr.run_id, cr.label, cr.model_id, cr.parent_span_id,
                cr.span_id,
                SUM(crc.call_cost) AS own_cost,
                SUM(crc.input_tokens) AS input_tokens,
                SUM(crc.output_tokens) AS output_tokens,
                qs.combined_score,
                CASE
                    WHEN qs.combined_score IS NULL THEN NULL
                    ELSE ROUND(
                        SUM(crc.call_cost) / MAX(qs.combined_score, 0.01), 4
                    )
                END AS cpqp
            FROM cost_runs cr
            JOIN cost_run_calls crc ON cr.run_id = crc.run_id
            LEFT JOIN quality_scores qs ON cr.run_id = qs.run_id
            WHERE cr.trace_id = ?
            GROUP BY cr.run_id
            ORDER BY cr.started_at ASC
            """,
            (trace_id,),
        ).fetchall()
    finally:
        conn.close()

    agents = [dict(r) for r in rows]
    for a in agents:
        a["own_cost"] = float(a["own_cost"] or 0.0)
        a["input_tokens"] = int(a["input_tokens"] or 0)
        a["output_tokens"] = int(a["output_tokens"] or 0)

    agent_map = {a["span_id"]: a for a in agents if a["span_id"]}

    children_map: dict[str, list[str]] = {}
    for a in agents:
        pid = a["parent_span_id"]
        if pid and pid in agent_map:
            children_map.setdefault(pid, []).append(a["span_id"])

    def roll_up(span_key: str, depth: int) -> float:
        agent = agent_map[span_key]
        agent["depth"] = depth
        child_total = 0.0
        for child_key in children_map.get(span_key, []):
            child_total += roll_up(child_key, depth + 1)
        agent["rolled_up_cost"] = agent["own_cost"] + child_total
        return agent["rolled_up_cost"]

    roots = [
        a
        for a in agents
        if a["parent_span_id"] is None or a["parent_span_id"] not in agent_map
    ]
    for root in roots:
        if root["span_id"]:
            roll_up(root["span_id"], 0)

    for a in agents:
        if "depth" not in a:
            a["depth"] = 0
            a["rolled_up_cost"] = a["own_cost"]

    total_cost = sum(a["own_cost"] for a in agents)
    total_input = sum(a["input_tokens"] for a in agents)
    total_output = sum(a["output_tokens"] for a in agents)

    return {
        "trace_id": trace_id,
        "agents": agents,
        "total_runs": len(agents),
        "total_cost": total_cost,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
    }
