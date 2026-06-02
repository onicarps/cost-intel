"""Configuration loader — reads ~/.cost-intel/config.yaml."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml

DEFAULT_CONFIG_DIR = Path.home() / ".cost-intel"
CONFIG_DIR = Path(os.environ.get("COST_INTEL_HOME", str(DEFAULT_CONFIG_DIR)))
CONFIG_PATH = CONFIG_DIR / "config.yaml"

_config_cache: Optional[dict[str, Any]] = None


def load_config(force_reload: bool = False) -> dict[str, Any]:
    """Load configuration from ~/.cost-intel/config.yaml.

    Args:
        force_reload: If True, ignore cache and re-read from disk.

    Returns:
        Configuration dict. Empty dict if file doesn't exist.
    """
    global _config_cache
    if _config_cache is not None and not force_reload:
        return _config_cache
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            _config_cache = yaml.safe_load(f) or {}
    else:
        _config_cache = {}
    return _config_cache


def get_eval_weights(source: str) -> Optional[dict[str, float]]:
    """Get evaluation weights for a specific source from config.

    Args:
        source: The eval source name (e.g., 'csv', 'eval_harness').

    Returns:
        Dictionary of dimension -> weight, or None if not configured.
    """
    cfg = load_config()
    eval_weights = cfg.get("eval_weights", {})
    return eval_weights.get(source)
