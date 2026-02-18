"""Tests for recorder module — device listing, resolution, WAV output."""

import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from liscribe.recorder import list_input_devices, resolve_device


class TestListInputDevices:
    def test_returns_list(self):
        devices = list_input_devices()
        assert isinstance(devices, list)

    def test_all_have_required_keys(self):
        devices = list_input_devices()
        for d in devices:
            assert "index" in d
            assert "name" in d
            assert "channels" in d
            assert "sample_rate" in d
            assert "is_default" in d

    def test_only_input_devices(self):
        devices = list_input_devices()
        for d in devices:
            assert d["channels"] > 0


class TestResolveDevice:
    def test_none_returns_none(self):
        assert resolve_device(None) is None

    def test_valid_index_string(self):
        devices = list_input_devices()
        if devices:
            idx = devices[0]["index"]
            assert resolve_device(str(idx)) == idx

    def test_invalid_index_raises(self):
        with pytest.raises(ValueError):
            resolve_device("9999")

    def test_name_match(self):
        devices = list_input_devices()
        if devices:
            name = devices[0]["name"]
            # Use first word of device name
            word = name.split()[0]
            result = resolve_device(word)
            assert result is not None

    def test_no_match_raises(self):
        with pytest.raises(ValueError):
            resolve_device("ZZZ_NONEXISTENT_DEVICE_XYZ")
