"""Tests for config module."""

from pathlib import Path
from unittest.mock import patch

from liscribe.config import load_config, DEFAULTS


class TestLoadConfig:
    def test_returns_dict(self):
        cfg = load_config()
        assert isinstance(cfg, dict)

    def test_has_all_default_keys(self):
        cfg = load_config()
        for key in DEFAULTS:
            assert key in cfg

    def test_default_sample_rate(self):
        cfg = load_config()
        assert cfg["sample_rate"] == 16000

    def test_default_channels(self):
        cfg = load_config()
        assert cfg["channels"] == 1
