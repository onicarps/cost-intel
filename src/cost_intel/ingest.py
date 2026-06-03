"""JSONL and CSV ingestion with provider-specific token extraction.

Supports:
- JSONL: OpenRouter, Anthropic, and OpenAI response formats
- CSV: Per-call exports and aggregated activity from OpenRouter dashboard
Handles cache token extraction from provider-specific usage fields.
"""

import csv
import json
from pathlib import Path
from typing import Optional

from cost_intel.db import init_db
from cost_intel.record import record_run


def _extract_tokens(usage: dict, format: str) -> dict:
    """Extract token counts from a usage object based on provider format.

    Args:
        usage: Usage dict from API response.
        format: Provider format ('openrouter', 'anthropic', 'openai').

    Returns:
        Dict with input_tokens, output_tokens, cache_read_tokens,
        cache_write_tokens.
    """
    result = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }

    if format == "anthropic":
        result["input_tokens"] = usage.get("input_tokens", 0)
        result["output_tokens"] = usage.get("output_tokens", 0)
        result["cache_read_tokens"] = usage.get("cache_read_input_tokens", 0)
        result["cache_write_tokens"] = usage.get("cache_creation_input_tokens", 0)
    elif format in ("openrouter", "openai"):
        result["input_tokens"] = usage.get("prompt_tokens", 0)
        result["output_tokens"] = usage.get("completion_tokens", 0)
        # Cache tokens in prompt_tokens_details
        details = usage.get("prompt_tokens_details", {})
        if details:
            result["cache_read_tokens"] = details.get("cached_tokens", 0)

    return result


def ingest_jsonl(
    file_path: str,
    format: str = "openrouter",
    label: Optional[str] = None,
) -> int:
    """Ingest cost runs from a JSONL file of API responses.

    Each line should be a JSON object with 'model' and 'usage' fields.
    Malformed lines are silently skipped.

    Args:
        file_path: Path to the JSONL file.
        format: Provider format for token extraction.
        label: Optional label applied to all ingested runs.

    Returns:
        Number of runs successfully ingested.
    """
    path = Path(file_path)
    if not path.exists():
        return 0

    init_db()
    count = 0

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue

            model = record.get("model", "unknown")
            usage = record.get("usage", {})
            tokens = _extract_tokens(usage, format)

            record_run(
                model_id=model,
                input_tokens=tokens["input_tokens"],
                output_tokens=tokens["output_tokens"],
                cache_read_tokens=tokens["cache_read_tokens"],
                cache_write_tokens=tokens["cache_write_tokens"],
                label=label,
                provider=model.split("/")[0] if "/" in model else "unknown",
            )
            count += 1

    return count


def _parse_cost(value: str) -> float:
    """Parse a cost value, stripping $ signs and commas."""
    if not value:
        return 0.0
    cleaned = value.strip().replace("$", "").replace(",", "")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _detect_csv_format(headers: list[str]) -> str:
    """Detect CSV format from headers.

    Returns:
        'per_call' for row-per-call format (has timestamp/model/input_tokens)
        'aggregated' for summary format (has Model/Min/Max/Avg/Sum)
    """
    h = [x.strip().lower() for x in headers]
    if "timestamp" in h and "model" in h and "input_tokens" in h:
        return "per_call"
    if "model" in h and "min" in h and "max" in h and "avg" in h and "sum" in h:
        return "aggregated"
    # Default: assume per-call if it has model + tokens
    if "model" in h and ("input_tokens" in h or "prompt_tokens" in h):
        return "per_call"
    return "per_call"


def ingest_csv(
    file_path: str,
    format: Optional[str] = None,
    source: Optional[str] = None,
    label: Optional[str] = None,
) -> int:
    """Ingest cost runs from a CSV file.

    Auto-detects format (per-call vs aggregated) unless ``format`` is specified.

    Per-call format expects columns like:
        timestamp, model, input_tokens, output_tokens, cost

    Aggregated format expects columns like:
        Model, Min, Max, Avg, Sum

    Args:
        file_path: Path to the CSV file.
        format: 'per_call' or 'aggregated'. Auto-detected if None.
        source: Optional source tag applied to all imported runs.
        label: Optional label applied to all imported runs.

    Returns:
        Number of runs successfully ingested.
    """
    path = Path(file_path)
    if not path.exists():
        return 0

    init_db()
    count = 0

    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return 0

        if format is None:
            fmt = _detect_csv_format(reader.fieldnames)
        else:
            fmt = format

        if fmt == "aggregated":
            count = _ingest_aggregated(reader, source=source, label=label)
        else:
            count = _ingest_per_call(reader, source=source, label=label)

    return count


def _ingest_per_call(
    reader,
    source: Optional[str] = None,
    label: Optional[str] = None,
) -> int:
    """Ingest per-call CSV rows."""
    count = 0
    for row in reader:
        model = (row.get("model") or row.get("Model") or "").strip()
        if not model:
            continue

        input_tokens_raw = (
            row.get("input_tokens")
            or row.get("prompt_tokens")
            or row.get("Input Tokens")
            or "0"
        )
        output_tokens_raw = (
            row.get("output_tokens")
            or row.get("completion_tokens")
            or row.get("Output Tokens")
            or "0"
        )
        cost_raw = row.get("cost") or row.get("Cost") or row.get("Sum") or ""
        timestamp = (
            row.get("timestamp")
            or row.get("Timestamp")
            or row.get("Date")
            or row.get("date")
            or None
        )

        try:
            input_tokens = int(input_tokens_raw)
            output_tokens = int(output_tokens_raw)
        except (ValueError, TypeError):
            continue

        cost = _parse_cost(cost_raw)

        parts = []
        if source:
            parts.append(source)
        if label:
            parts.append(label)
        combined_label = ":".join(parts) if parts else None

        if cost > 0:
            _record_with_cost(
                model,
                input_tokens,
                output_tokens,
                cost,
                timestamp=timestamp,
                label=combined_label,
            )
        else:
            record_run(
                model_id=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                label=combined_label,
                provider=model.split("/")[0] if "/" in model else "unknown",
            )
        count += 1

    return count


def _ingest_aggregated(
    reader,
    source: Optional[str] = None,
    label: Optional[str] = None,
) -> int:
    """Ingest aggregated CSV rows (per-model summary)."""
    count = 0
    for row in reader:
        model = (row.get("Model") or row.get("model") or "").strip()
        if not model:
            continue

        sum_raw = (
            row.get("Sum")
            or row.get("sum")
            or row.get("Total")
            or row.get("total")
            or ""
        )

        total_cost = _parse_cost(sum_raw)

        parts = ["aggregated"]
        if source:
            parts.append(source)
        if label:
            parts.append(label)
        combined_label = ":".join(parts)

        _record_with_cost(
            model=model,
            input_tokens=0,
            output_tokens=0,
            cost=total_cost,
            timestamp=None,
            label=combined_label,
        )
        count += 1

    return count


def _record_with_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
    timestamp: Optional[str] = None,
    label: Optional[str] = None,
) -> str:
    """Record a run with an explicit cost (bypassing price lookup)."""
    import uuid

    from cost_intel.db import get_connection
    from cost_intel.utils import now_iso

    rid = str(uuid.uuid4())
    ts = timestamp if timestamp else now_iso()
    prov = model.split("/")[0] if "/" in model else "unknown"

    conn = get_connection()
    conn.execute(
        "INSERT INTO cost_runs "
        "(run_id, run_type, label, model_id, started_at, "
        "finished_at, status) "
        "VALUES (?, 'api_call', ?, ?, ?, ?, 'completed')",
        (rid, label, model, ts, ts),
    )
    conn.execute(
        "INSERT INTO cost_run_calls "
        "(run_id, sequence, provider, model, input_tokens, "
        "output_tokens, cache_read_tokens, cache_write_tokens, "
        "call_cost, latency_ms, raw_response) "
        "VALUES (?, 0, ?, ?, ?, ?, 0, 0, ?, NULL, NULL)",
        (rid, prov, model, input_tokens, output_tokens, cost),
    )
    conn.commit()
    conn.close()
    return rid
