"""Tests for prompt optimization analysis."""

from cost_intel.db import init_db
from cost_intel.pricing import upsert_pricing
from cost_intel.prompt_opt import analyze_prompt_patterns, suggest_trimming
from cost_intel.record import record_run


def test_analyze_prompt_patterns(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    for _ in range(5):
        record_run("openai/gpt-4o", 5000, 2000, label="summarize-doc")
    for _ in range(5):
        record_run("openai/gpt-4o", 100, 50, label="classify-sentiment")

    results = analyze_prompt_patterns(top_n=5)

    assert len(results) > 0
    top = results[0]
    assert "summarize" in top["label_prefix"]
    assert top["avg_cost"] > 10.0
    assert top["total_runs"] == 5
    assert top["avg_input_tokens"] == 5000
    assert top["avg_output_tokens"] == 2000


def test_analyze_prompt_patterns_orders_by_avg_cost_desc(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    for _ in range(3):
        record_run("openai/gpt-4o", 100, 50, label="cheap-task")
    for _ in range(3):
        record_run("openai/gpt-4o", 8000, 4000, label="expensive-task")

    results = analyze_prompt_patterns(top_n=10)
    prefixes = [r["label_prefix"] for r in results]

    assert prefixes.index("expensive") < prefixes.index("cheap")


def test_analyze_prompt_patterns_excludes_singletons(tmp_cost_intel_home):
    """Prefixes with fewer than 2 runs must be excluded."""
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    record_run("openai/gpt-4o", 9999, 9999, label="loner-task")
    for _ in range(2):
        record_run("openai/gpt-4o", 100, 50, label="common-task")

    results = analyze_prompt_patterns()
    prefixes = [r["label_prefix"] for r in results]

    assert "loner" not in prefixes
    assert "common" in prefixes


def test_analyze_prompt_patterns_handles_underscore_prefix(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    for _ in range(2):
        record_run("openai/gpt-4o", 200, 100, label="rag_lookup")

    results = analyze_prompt_patterns()
    prefixes = [r["label_prefix"] for r in results]

    assert "rag" in prefixes


def test_suggest_trimming(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    for _ in range(3):
        record_run("openai/gpt-4o", 10000, 500, label="summarize-long")

    suggestions = suggest_trimming(threshold_tokens=5000)

    assert len(suggestions) > 0
    assert suggestions[0]["avg_input_tokens"] > 5000
    msg = suggestions[0]["suggestion"].lower()
    assert "trim" in msg or "reduce" in msg


def test_suggest_trimming_no_matches_returns_empty(tmp_cost_intel_home):
    init_db()
    upsert_pricing("openai/gpt-4o", "openai", 2.5, 10.0)
    for _ in range(2):
        record_run("openai/gpt-4o", 100, 50, label="tiny-task")

    suggestions = suggest_trimming(threshold_tokens=5000)

    assert suggestions == []
