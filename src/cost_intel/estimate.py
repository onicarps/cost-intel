"""Token estimation using tiktoken for pre-call cost prediction."""

from typing import Optional

import tiktoken

from cost_intel.pricing import get_pricing


def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    """Estimate token count for a given text and model.

    Args:
        text: The text to estimate tokens for.
        model: Model name (used to select tokenizer).

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to cl100k_base (used by gpt-4, gpt-3.5-turbo, etc.)
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def estimate_cost(
    text: str,
    model: str,
    provider: Optional[str] = None,
) -> dict:
    """Estimate cost for a given text and model.

    Args:
        text: The input text.
        model: Model identifier (e.g., 'openai/gpt-4o').
        provider: Provider name (auto-detected if None).

    Returns:
        Dict with input_tokens, estimated_cost, model_id.
    """
    model_name = model.split("/")[-1] if "/" in model else model
    tokens = estimate_tokens(text, model=model_name)
    pricing = get_pricing(model)

    if pricing and tokens > 0:
        cost = (tokens / 1000) * (pricing["input_price_per_1k_tokens"] or 0)
    else:
        cost = 0.0

    return {
        "input_tokens": tokens,
        "estimated_cost": round(cost, 6),
        "model_id": model,
    }
