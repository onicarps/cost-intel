"""Tests for config.py."""

from pathlib import Path

from cost_intel.config import get_eval_weights, load_config


def test_load_config_returns_empty_dict_when_no_file(tmp_path, monkeypatch):
    """Config loader returns empty dict when config.yaml doesn't exist."""
    monkeypatch.setattr("cost_intel.config.CONFIG_PATH", tmp_path / "config.yaml")
    # Clear cache
    import cost_intel.config as cfg_mod

    cfg_mod._config_cache = None
    result = load_config(force_reload=True)
    assert result == {}


def test_load_config_reads_yaml_file(tmp_path, monkeypatch):
    """Config loader reads and parses YAML config file."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("eval_weights:\n  csv:\n    score: 1.0\n")
    monkeypatch.setattr("cost_intel.config.CONFIG_PATH", config_file)
    import cost_intel.config as cfg_mod

    cfg_mod._config_cache = None
    result = load_config(force_reload=True)
    assert result["eval_weights"]["csv"]["score"] == 1.0


def test_load_config_caches(monkeypatch):
    """Config loader caches results on subsequent calls."""
    monkeypatch.setattr(
        "cost_intel.config.CONFIG_PATH", Path("/nonexistent/config.yaml")
    )
    import cost_intel.config as cfg_mod

    cfg_mod._config_cache = None
    load_config()
    # Second call should return cached value without re-reading
    assert load_config() == {}


def test_get_eval_weights_returns_weights_for_source(tmp_path, monkeypatch):
    """get_eval_weights returns weights dict for a given source."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "eval_weights:\n  csv:\n    score: 0.8\n    relevance: 0.2\n"
    )
    monkeypatch.setattr("cost_intel.config.CONFIG_PATH", config_file)
    import cost_intel.config as cfg_mod

    cfg_mod._config_cache = None
    weights = get_eval_weights("csv")
    assert weights == {"score": 0.8, "relevance": 0.2}


def test_get_eval_weights_returns_none_for_missing_source(tmp_path, monkeypatch):
    """get_eval_weights returns None when source not in config."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("eval_weights:\n  csv:\n    score: 1.0\n")
    monkeypatch.setattr("cost_intel.config.CONFIG_PATH", config_file)
    import cost_intel.config as cfg_mod

    cfg_mod._config_cache = None
    assert get_eval_weights("braintrust") is None
