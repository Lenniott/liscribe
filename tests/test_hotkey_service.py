"""Tests for HotkeyService — dictate double-tap and hold state machine."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from liscribe.services.config_service import ConfigService
from liscribe.services.hotkey_service import (
    HotkeyService,
    _DOUBLE_TAP_WINDOW,
    _HOLD_THRESHOLD,
)


@pytest.fixture()
def mock_config():
    cfg = MagicMock(spec=ConfigService)
    cfg.get.return_value = None
    return cfg


@pytest.fixture()
def svc(mock_config):
    return HotkeyService(mock_config)


@pytest.fixture(autouse=True)
def cancel_hold_timer(svc):
    """Ensure any pending Timer is cancelled after each test."""
    yield
    if svc._hold_timer is not None:
        svc._hold_timer.cancel()
        svc._hold_timer = None


# ---------------------------------------------------------------------------
# Double-tap → toggle
# ---------------------------------------------------------------------------

class TestDoubleTap:
    def test_two_quick_taps_fire_toggle(self, svc):
        toggle = MagicMock()
        svc._on_dictate_toggle = toggle

        svc._on_dictate_key_press()
        time.sleep(0.05)
        svc._on_dictate_key_press()

        toggle.assert_called_once()

    def test_single_tap_does_not_fire_toggle(self, svc):
        toggle = MagicMock()
        svc._on_dictate_toggle = toggle

        svc._on_dictate_key_press()

        toggle.assert_not_called()

    def test_slow_taps_do_not_fire_toggle(self, svc):
        toggle = MagicMock()
        svc._on_dictate_toggle = toggle

        svc._on_dictate_key_press()
        time.sleep(_DOUBLE_TAP_WINDOW + 0.05)
        svc._on_dictate_key_press()

        toggle.assert_not_called()

    def test_triple_tap_fires_toggle_only_once(self, svc):
        """Second tap fires toggle; third tap starts a new single-tap cycle."""
        toggle = MagicMock()
        svc._on_dictate_toggle = toggle

        svc._on_dictate_key_press()
        time.sleep(0.05)
        svc._on_dictate_key_press()  # fires toggle
        time.sleep(0.05)
        svc._on_dictate_key_press()  # starts new single-tap, no toggle yet

        assert toggle.call_count == 1


# ---------------------------------------------------------------------------
# Hold → hold_start / hold_end
# ---------------------------------------------------------------------------

class TestHold:
    def test_hold_fires_hold_start(self, svc):
        hold_start = MagicMock()
        svc._on_dictate_hold_start = hold_start

        svc._on_dictate_key_press()
        time.sleep(_HOLD_THRESHOLD + 0.05)

        hold_start.assert_called_once()

    def test_release_after_hold_fires_hold_end(self, svc):
        hold_end = MagicMock()
        svc._on_dictate_hold_end = hold_end

        svc._on_dictate_key_press()
        time.sleep(_HOLD_THRESHOLD + 0.05)
        svc._on_dictate_key_release()

        hold_end.assert_called_once()

    def test_release_before_threshold_does_not_fire_hold_end(self, svc):
        hold_end = MagicMock()
        svc._on_dictate_hold_end = hold_end

        svc._on_dictate_key_press()
        time.sleep(0.05)  # well before _HOLD_THRESHOLD
        svc._on_dictate_key_release()

        hold_end.assert_not_called()

    def test_hold_fires_hold_start_not_toggle(self, svc):
        """Holding should not trigger toggle even though it starts with a press."""
        toggle = MagicMock()
        hold_start = MagicMock()
        svc._on_dictate_toggle = toggle
        svc._on_dictate_hold_start = hold_start

        svc._on_dictate_key_press()
        time.sleep(_HOLD_THRESHOLD + 0.05)

        toggle.assert_not_called()
        hold_start.assert_called_once()


# ---------------------------------------------------------------------------
# State reset between interactions
# ---------------------------------------------------------------------------

class TestStateReset:
    def test_tap_after_hold_does_not_double_tap(self, svc):
        """A tap after a hold session should start a fresh tap window."""
        toggle = MagicMock()
        svc._on_dictate_toggle = toggle

        # hold session
        svc._on_dictate_key_press()
        time.sleep(_HOLD_THRESHOLD + 0.05)
        svc._on_dictate_key_release()

        # now a single tap — should NOT trigger toggle
        svc._on_dictate_key_press()
        time.sleep(0.05)

        toggle.assert_not_called()

    def test_in_hold_mode_reset_after_release(self, svc):
        svc._on_dictate_key_press()
        time.sleep(_HOLD_THRESHOLD + 0.05)
        assert svc._in_hold_mode is True
        svc._on_dictate_key_release()
        assert svc._in_hold_mode is False


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_start_registers_callbacks(self, svc):
        cb = MagicMock()
        svc.start(on_scribe=cb)
        assert svc._on_scribe is cb

    def test_start_without_pynput_does_not_raise(self, svc):
        import liscribe.services.hotkey_service as hs_module
        original = hs_module._PYNPUT_AVAILABLE
        try:
            hs_module._PYNPUT_AVAILABLE = False
            svc.start()  # must not raise
        finally:
            hs_module._PYNPUT_AVAILABLE = original

    def test_stop_on_idle_is_safe(self, svc):
        svc.stop()  # must not raise when listener is None
