"""JSONL ingestion with provider-specific token extraction.

Supports OpenRouter, Anthropic, and OpenAI response formats.
Handles cache token extraction from provider-specific usage fields.
"""

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
