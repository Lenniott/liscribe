"""Tests for DictateBridge — JS-to-Python call translation for Dictate panel.

Bridge must delegate to controller; no business logic.
Returns JSON-serialisable values; surfaces errors to the caller.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from liscribe.bridge.dictate_bridge import DictateBridge
from liscribe.controllers.dictate_controller import DictateState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def controller():
    ctrl = MagicMock()
    ctrl.state = DictateState.IDLE
    ctrl.is_recording = False
    ctrl.get_waveform.return_value = [0.5] * 30
    ctrl.get_elapsed.return_value = 3.0
    ctrl.get_ui_state.return_value = "idle"
    return ctrl


@pytest.fixture()
def bridge(controller):
    return DictateBridge(controller=controller)


# ---------------------------------------------------------------------------
# get_waveform()
# ---------------------------------------------------------------------------


class TestGetWaveform:
    def test_delegates_to_controller(self, bridge, controller):
        bridge.get_waveform()
        controller.get_waveform.assert_called_once()

    def test_returns_list(self, bridge):
        result = bridge.get_waveform()
        assert isinstance(result, list)

    def test_passes_bars_argument(self, bridge, controller):
        bridge.get_waveform(bars=20)
        controller.get_waveform.assert_called_once_with(bars=20)

    def test_returns_controller_values(self, bridge, controller):
        controller.get_waveform.return_value = [0.1, 0.2, 0.3]
        result = bridge.get_waveform(bars=3)
        assert result == [0.1, 0.2, 0.3]

    def test_returns_empty_list_on_error(self, bridge, controller):
        controller.get_waveform.side_effect = RuntimeError("boom")
        result = bridge.get_waveform()
        assert result == []


# ---------------------------------------------------------------------------
# get_elapsed()
# ---------------------------------------------------------------------------


class TestGetElapsed:
    def test_delegates_to_controller(self, bridge, controller):
        bridge.get_elapsed()
        controller.get_elapsed.assert_called_once()

    def test_returns_float(self, bridge):
        result = bridge.get_elapsed()
        assert isinstance(result, float)

    def test_returns_controller_value(self, bridge, controller):
        controller.get_elapsed.return_value = 7.5
        result = bridge.get_elapsed()
        assert result == 7.5

    def test_returns_zero_on_error(self, bridge, controller):
        controller.get_elapsed.side_effect = RuntimeError("boom")
        result = bridge.get_elapsed()
        assert result == 0.0


# ---------------------------------------------------------------------------
# get_state()
# ---------------------------------------------------------------------------


class TestGetState:
    def test_delegates_to_controller(self, bridge, controller):
        bridge.get_state()
        controller.get_ui_state.assert_called_once()

    def test_returns_controller_value(self, bridge, controller):
        controller.get_ui_state.return_value = "processing"
        assert bridge.get_state() == "processing"

    def test_returns_idle_on_error(self, bridge, controller):
        controller.get_ui_state.side_effect = RuntimeError("boom")
        assert bridge.get_state() == "idle"
