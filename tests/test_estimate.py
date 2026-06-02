"""Tests for estimate module — tiktoken pre-call estimation."""

from cost_intel.estimate import estimate_cost, estimate_tokens


class TestEstimateTokens:
    """Tests for estimate_tokens."""

    def test_estimate_basic_text(self, tmp_cost_intel_home):
        """estimate_tokens returns token count for text."""
        count = estimate_tokens("Hello, world!", model="gpt-4")
        assert isinstance(count, int)
        assert count > 0

    def test_estimate_empty_string(self, tmp_cost_intel_home):
        """estimate_tokens returns 0 for empty string."""
        count = estimate_tokens("", model="gpt-4")
        assert count == 0

    def test_estimate_longer_text_more_tokens(self, tmp_cost_intel_home):
        """Longer text produces more tokens."""
        short = estimate_tokens("Hi", model="gpt-4")
        long_text = estimate_tokens(
            "This is a much longer text that should produce "
            "significantly more tokens than just a short greeting.",
            model="gpt-4",
        )
        assert long_text > short


class TestEstimateCost:
    """Tests for estimate_cost."""

    def test_estimate_cost_with_pricing(self, tmp_cost_intel_home):
        """estimate_cost computes cost from token estimate + pricing."""
        from cost_intel.db import init_db
        from cost_intel.pricing import upsert_pricing

        init_db()
        upsert_pricing("openai/gpt-4o", "openai", 30.0, 60.0)

        result = estimate_cost(
            "Hello world. This is a test.",
            model="openai/gpt-4o",
        )
        assert result["input_tokens"] > 0
        assert result["estimated_cost"] > 0
        assert result["model_id"] == "openai/gpt-4o"

    def test_estimate_cost_unknown_model(self, tmp_cost_intel_home):
        """estimate_cost returns cost=0 for unknown model."""
        from cost_intel.db import init_db

        init_db()
        result = estimate_cost(
            "Hello world",
            model="unknown/model",
        )
        assert result["estimated_cost"] == 0.0
