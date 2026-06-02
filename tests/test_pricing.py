"""Tests for pricing module."""

from unittest.mock import patch

from cost_intel.pricing import (
    get_pricing,
    refresh_all_pricing,
    set_manual_pricing,
    upsert_pricing,
)


class TestUpsertPricing:
    """Tests for upsert_pricing."""

    def test_insert_new_pricing(self, tmp_cost_intel_home):
        """Insert pricing for a new model."""
        from cost_intel.db import init_db

        init_db()
        upsert_pricing("openai/gpt-4o", "openai", 30.0, 60.0)
        p = get_pricing("openai/gpt-4o")
        assert p is not None
        assert p["input_price_per_1k_tokens"] == 30.0
        assert p["output_price_per_1k_tokens"] == 60.0
        assert p["source"] == "openrouter"
        assert p["is_current"] == 1

    def test_update_preserves_old_row(self, tmp_cost_intel_home):
        """When prices change on a later day, old row gets is_current=0."""
        from cost_intel.db import get_connection, init_db

        init_db()
        # Insert first pricing row manually on a past date
        conn = get_connection()
        conn.execute(
            "INSERT INTO model_pricing "
            "(model_id, provider, input_price_per_1k_tokens, "
            "output_price_per_1k_tokens, effective_date, "
            "is_current, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("openai/gpt-4o", "openai", 30.0, 60.0, "2026-01-01", 1, "openrouter"),
        )
        conn.commit()
        conn.close()

        # Upsert with new price (today's date) should preserve old
        upsert_pricing("openai/gpt-4o", "openai", 25.0, 50.0)

        # Current should be the new price
        p = get_pricing("openai/gpt-4o")
        assert p["input_price_per_1k_tokens"] == 25.0

        # Old row should still exist with is_current=0
        conn = get_connection()
        rows = conn.execute(
            "SELECT COUNT(*) as cnt FROM model_pricing "
            "WHERE model_id = ? AND is_current = 0",
            ("openai/gpt-4o",),
        ).fetchone()
        assert rows["cnt"] == 1
        conn.close()

    def test_same_day_update_in_place(self, tmp_cost_intel_home):
        """Two upserts on the same day update in place (no duplicate)."""
        from cost_intel.db import get_connection, init_db

        init_db()
        upsert_pricing("openai/gpt-4o", "openai", 30.0, 60.0)
        upsert_pricing("openai/gpt-4o", "openai", 25.0, 50.0)

        # Current should be the latest price
        p = get_pricing("openai/gpt-4o")
        assert p["input_price_per_1k_tokens"] == 25.0

        # Only one row (same-day upsert updates in place)
        conn = get_connection()
        rows = conn.execute(
            "SELECT COUNT(*) as cnt FROM model_pricing WHERE model_id = ?",
            ("openai/gpt-4o",),
        ).fetchone()
        assert rows["cnt"] == 1
        conn.close()

    def test_no_change_is_noop(self, tmp_cost_intel_home):
        """Upserting identical prices doesn't create a new row."""
        from cost_intel.db import get_connection, init_db

        init_db()
        upsert_pricing("openai/gpt-4o", "openai", 30.0, 60.0)
        upsert_pricing("openai/gpt-4o", "openai", 30.0, 60.0)

        conn = get_connection()
        rows = conn.execute(
            "SELECT COUNT(*) as cnt FROM model_pricing WHERE model_id = ?",
            ("openai/gpt-4o",),
        ).fetchone()
        assert rows["cnt"] == 1
        conn.close()

    def test_cache_pricing_stored(self, tmp_cost_intel_home):
        """Cache token pricing is stored when provided."""
        from cost_intel.db import init_db

        init_db()
        upsert_pricing(
            "anthropic/claude-sonnet-4",
            "anthropic",
            3.0,
            15.0,
            cache_read=0.3,
            cache_write=3.75,
        )
        p = get_pricing("anthropic/claude-sonnet-4")
        assert p["cache_read_price_per_1k_tokens"] == 0.3
        assert p["cache_write_price_per_1k_tokens"] == 3.75


class TestGetPricing:
    """Tests for get_pricing."""

    def test_returns_none_for_unknown_model(self, tmp_cost_intel_home):
        """Returns None for a model with no pricing."""
        from cost_intel.db import init_db

        init_db()
        assert get_pricing("unknown/model") is None

    def test_historical_pricing_by_date(self, tmp_cost_intel_home):
        """get_pricing with as_of_date returns correct historical price."""
        from cost_intel.db import get_connection, init_db

        init_db()
        conn = get_connection()
        # Insert two pricing rows manually with specific dates
        conn.execute(
            "INSERT INTO model_pricing "
            "(model_id, provider, input_price_per_1k_tokens, "
            "output_price_per_1k_tokens, effective_date, is_current, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("openai/gpt-4o", "openai", 30.0, 60.0, "2026-01-01", 0, "openrouter"),
        )
        conn.execute(
            "INSERT INTO model_pricing "
            "(model_id, provider, input_price_per_1k_tokens, "
            "output_price_per_1k_tokens, effective_date, is_current, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("openai/gpt-4o", "openai", 25.0, 50.0, "2026-06-01", 1, "openrouter"),
        )
        conn.commit()
        conn.close()

        # Query at old date
        p_old = get_pricing("openai/gpt-4o", as_of_date="2026-03-01")
        assert p_old["input_price_per_1k_tokens"] == 30.0

        # Query at current date
        p_new = get_pricing("openai/gpt-4o", as_of_date="2026-06-15")
        assert p_new["input_price_per_1k_tokens"] == 25.0


class TestSetManualPricing:
    """Tests for set_manual_pricing."""

    def test_manual_pricing_source(self, tmp_cost_intel_home):
        """set_manual_pricing stores with source='manual'."""
        from cost_intel.db import init_db

        init_db()
        set_manual_pricing("custom/my-model", "custom", 10.0, 20.0)
        p = get_pricing("custom/my-model")
        assert p["source"] == "manual"


class TestRefreshAllPricing:
    """Tests for refresh_all_pricing."""

    def test_refresh_inserts_models(self, tmp_cost_intel_home):
        """refresh_all_pricing fetches and stores model pricing."""
        from cost_intel.db import init_db

        init_db()
        mock_data = [
            {
                "id": "openai/gpt-4o",
                "pricing": {"prompt": 0.00003, "completion": 0.00006},
            },
        ]
        with patch(
            "cost_intel.pricing.fetch_openrouter_pricing",
            return_value=mock_data,
        ):
            count = refresh_all_pricing()
        assert count == 1
        p = get_pricing("openai/gpt-4o")
        assert p is not None
        # 0.00003 * 1_000_000 = 30.0 (per-million → per-1K)
        assert p["input_price_per_1k_tokens"] == 30.0

    def test_refresh_skips_models_without_slash(self, tmp_cost_intel_home):
        """Models without provider/ prefix are skipped."""
        from cost_intel.db import init_db

        init_db()
        mock_data = [
            {
                "id": "no-slash-model",
                "pricing": {"prompt": 0.00003, "completion": 0.00006},
            },
        ]
        with patch(
            "cost_intel.pricing.fetch_openrouter_pricing",
            return_value=mock_data,
        ):
            count = refresh_all_pricing()
        assert count == 0

    def test_refresh_skips_zero_pricing(self, tmp_cost_intel_home):
        """Models with zero pricing are skipped."""
        from cost_intel.db import init_db

        init_db()
        mock_data = [
            {
                "id": "openai/free-model",
                "pricing": {"prompt": 0, "completion": 0},
            },
        ]
        with patch(
            "cost_intel.pricing.fetch_openrouter_pricing",
            return_value=mock_data,
        ):
            count = refresh_all_pricing()
        assert count == 0
