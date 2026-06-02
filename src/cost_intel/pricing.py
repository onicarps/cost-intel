"""Model pricing with historical tracking, retry/backoff, refresh CLI.

Pricing is stored with composite PK (model_id, effective_date) to
preserve historical pricing rows. When prices change, the old row's
is_current is set to 0 and a new row is inserted.

OpenRouter returns pricing per-million tokens, so we multiply by 1_000_000
to get per-1K-token pricing.
"""

import os
from datetime import datetime, timezone
from typing import Optional

import httpx

from cost_intel.db import get_connection
from cost_intel.utils import retry

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def fetch_openrouter_pricing() -> list[dict]:
    """Fetch model pricing from OpenRouter /models API.

    Uses retry with exponential backoff (3 attempts).

    Returns:
        List of model dicts from the OpenRouter API.
    """

    def _do_fetch() -> list[dict]:
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp = httpx.get(OPENROUTER_MODELS_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json().get("data", [])

    return retry(_do_fetch, max_attempts=3, delay=1.0)


def upsert_pricing(
    model_id: str,
    provider: str,
    input_price: float,
    output_price: float,
    cache_read: Optional[float] = None,
    cache_write: Optional[float] = None,
    source: str = "openrouter",
) -> None:
    """Insert or update pricing. If prices changed, preserves old row.

    Same-day re-upsert updates in place (no duplicate PK violation).
    Different-day upsert marks old row is_current=0 and inserts new.

    Args:
        model_id: Model identifier (e.g., 'openai/gpt-4o').
        provider: Provider name (e.g., 'openai').
        input_price: Input price per 1K tokens.
        output_price: Output price per 1K tokens.
        cache_read: Cache read price per 1K tokens.
        cache_write: Cache write price per 1K tokens.
        source: Pricing source ('openrouter', 'manual', 'custom').
    """
    conn = get_connection()
    current = conn.execute(
        "SELECT * FROM model_pricing WHERE model_id = ? AND is_current = 1",
        (model_id,),
    ).fetchone()

    if current and (
        current["input_price_per_1k_tokens"] == input_price
        and current["output_price_per_1k_tokens"] == output_price
    ):
        conn.close()
        return  # No change

    now = datetime.now(timezone.utc).isoformat()
    today = now[:10]

    # Check if there's already a row for this model+date
    existing_today = conn.execute(
        "SELECT * FROM model_pricing WHERE model_id = ? AND effective_date = ?",
        (model_id, today),
    ).fetchone()

    if existing_today:
        # Same day: update the existing row in place
        conn.execute(
            "UPDATE model_pricing SET "
            "input_price_per_1k_tokens = ?, "
            "output_price_per_1k_tokens = ?, "
            "cache_read_price_per_1k_tokens = ?, "
            "cache_write_price_per_1k_tokens = ?, "
            "is_current = 1, source = ?, updated_at = ? "
            "WHERE model_id = ? AND effective_date = ?",
            (
                input_price,
                output_price,
                cache_read,
                cache_write,
                source,
                now,
                model_id,
                today,
            ),
        )
    else:
        # New day: mark old current as non-current, insert new row
        conn.execute(
            "UPDATE model_pricing SET is_current = 0 "
            "WHERE model_id = ? AND is_current = 1",
            (model_id,),
        )
        conn.execute(
            "INSERT INTO model_pricing "
            "(model_id, provider, input_price_per_1k_tokens, "
            "output_price_per_1k_tokens, cache_read_price_per_1k_tokens, "
            "cache_write_price_per_1k_tokens, effective_date, "
            "is_current, source, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (
                model_id,
                provider,
                input_price,
                output_price,
                cache_read,
                cache_write,
                today,
                source,
                now,
            ),
        )
    conn.commit()
    conn.close()


def get_pricing(model_id: str, as_of_date: Optional[str] = None) -> Optional[dict]:
    """Get pricing effective on a specific date.

    Args:
        model_id: Model identifier.
        as_of_date: Date string (YYYY-MM-DD). If None, returns current.

    Returns:
        Pricing dict or None if not found.
    """
    conn = get_connection()
    if as_of_date:
        row = conn.execute(
            "SELECT * FROM model_pricing "
            "WHERE model_id = ? AND effective_date <= ? "
            "ORDER BY effective_date DESC LIMIT 1",
            (model_id, as_of_date),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM model_pricing WHERE model_id = ? AND is_current = 1",
            (model_id,),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def refresh_all_pricing() -> int:
    """Refresh model pricing from OpenRouter API.

    OpenRouter returns prices per-million tokens. We convert to
    per-1K tokens by multiplying by 1_000_000 / 1_000 = 1_000.

    Returns:
        Number of models with pricing updated/inserted.
    """
    models = fetch_openrouter_pricing()
    count = 0
    for model in models:
        model_id = model.get("id", "")
        if "/" not in model_id:
            continue
        provider = model_id.split("/")[0]
        pricing = model.get("pricing", {})
        try:
            # OpenRouter returns per-million-token pricing
            # Convert to per-1K: multiply by 1_000_000
            input_price = float(pricing.get("prompt", 0)) * 1_000_000
            output_price = float(pricing.get("completion", 0)) * 1_000_000
        except (ValueError, TypeError):
            continue
        if input_price > 0 or output_price > 0:
            upsert_pricing(model_id, provider, input_price, output_price)
            count += 1
    return count


def set_manual_pricing(
    model_id: str,
    provider: str,
    input_price: float,
    output_price: float,
    cache_read: Optional[float] = None,
    cache_write: Optional[float] = None,
) -> None:
    """Set manual pricing for a private/enterprise model.

    Args:
        model_id: Model identifier.
        provider: Provider name.
        input_price: Input price per 1K tokens.
        output_price: Output price per 1K tokens.
        cache_read: Cache read price per 1K tokens.
        cache_write: Cache write price per 1K tokens.
    """
    upsert_pricing(
        model_id,
        provider,
        input_price,
        output_price,
        cache_read,
        cache_write,
        source="manual",
    )
