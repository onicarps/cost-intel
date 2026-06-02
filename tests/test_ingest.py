"""Tests for ingest module — JSONL ingestion with provider cache extraction."""

import json

from cost_intel.ingest import _extract_tokens, ingest_jsonl


class TestExtractTokens:
    """Tests for _extract_tokens helper."""

    def test_openrouter_format(self):
        """Extract tokens from OpenRouter-format usage."""
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
        }
        extracted = _extract_tokens(usage, "openrouter")
        assert extracted["input_tokens"] == 100
        assert extracted["output_tokens"] == 50
        assert extracted["cache_read_tokens"] == 0
        assert extracted["cache_write_tokens"] == 0

    def test_openrouter_with_cache(self):
        """Extract cache tokens from OpenRouter format."""
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 30},
        }
        extracted = _extract_tokens(usage, "openrouter")
        assert extracted["cache_read_tokens"] == 30

    def test_anthropic_format(self):
        """Extract tokens from Anthropic-format usage."""
        usage = {
            "input_tokens": 200,
            "output_tokens": 100,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 25,
        }
        extracted = _extract_tokens(usage, "anthropic")
        assert extracted["input_tokens"] == 200
        assert extracted["output_tokens"] == 100
        assert extracted["cache_read_tokens"] == 50
        assert extracted["cache_write_tokens"] == 25

    def test_openai_format(self):
        """Extract tokens from OpenAI-format usage."""
        usage = {
            "prompt_tokens": 150,
            "completion_tokens": 75,
            "prompt_tokens_details": {"cached_tokens": 40},
        }
        extracted = _extract_tokens(usage, "openai")
        assert extracted["input_tokens"] == 150
        assert extracted["output_tokens"] == 75
        assert extracted["cache_read_tokens"] == 40

    def test_unknown_format(self):
        """Unknown format returns zeros."""
        usage = {"some_field": 123}
        extracted = _extract_tokens(usage, "unknown")
        assert extracted["input_tokens"] == 0
        assert extracted["output_tokens"] == 0


class TestIngestJsonl:
    """Tests for ingest_jsonl."""

    def test_ingest_basic(self, tmp_cost_intel_home):
        """Ingest a JSONL file and verify runs recorded."""
        from cost_intel.db import init_db

        init_db()
        # Create a temp JSONL file
        lines = [
            json.dumps(
                {
                    "model": "test/model",
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                    },
                }
            ),
            json.dumps(
                {
                    "model": "test/model",
                    "usage": {
                        "prompt_tokens": 200,
                        "completion_tokens": 100,
                    },
                }
            ),
        ]
        jsonl_path = tmp_cost_intel_home / "test.jsonl"
        jsonl_path.write_text("\n".join(lines))

        count = ingest_jsonl(str(jsonl_path), format="openrouter")
        assert count == 2

    def test_ingest_skips_invalid_lines(self, tmp_cost_intel_home):
        """Malformed JSON lines are skipped."""
        from cost_intel.db import init_db

        init_db()
        lines = [
            json.dumps(
                {
                    "model": "test/model",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
            ),
            "not valid json",
            json.dumps(
                {
                    "model": "test/model",
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10},
                }
            ),
        ]
        jsonl_path = tmp_cost_intel_home / "test.jsonl"
        jsonl_path.write_text("\n".join(lines))

        count = ingest_jsonl(str(jsonl_path), format="openrouter")
        assert count == 2

    def test_ingest_with_label(self, tmp_cost_intel_home):
        """Ingest with label applied to all runs."""
        from cost_intel.db import init_db

        init_db()
        lines = [
            json.dumps(
                {
                    "model": "test/model",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
            ),
        ]
        jsonl_path = tmp_cost_intel_home / "test.jsonl"
        jsonl_path.write_text("\n".join(lines))

        count = ingest_jsonl(
            str(jsonl_path),
            format="openrouter",
            label="ingest-test",
        )
        assert count == 1

    def test_ingest_nonexistent_file(self, tmp_cost_intel_home):
        """Ingesting a nonexistent file returns 0."""
        count = ingest_jsonl("/nonexistent/file.jsonl")
        assert count == 0
