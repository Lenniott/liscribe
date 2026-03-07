"""Tests for HotkeyService — dictate key state machine.

Gesture rules:
  - Quick press+release (< _HOLD_THRESHOLD): counts as a "tap".
  - First tap sets _after_first_tap; second tap fires on_dictate_toggle (toggle recording).
  - Tap then second press held >= _HOLD_THRESHOLD: fires on_dictate_hold_start (hold recording).
  - Long first press from idle does nothing (tap required first).
  - While in toggle recording, any press+release fires on_dictate_single_release (stop).
  - While in hold recording, key-repeat presses are ignored; release fires on_dictate_hold_end.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from liscribe.services.config_service import ConfigService
from liscribe.services.hotkey_service import (
    HotkeyService,
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
def cancel_timers(svc):
    """Cancel any pending timers after each test to keep tests independent."""
    yield
    if svc._hold_timer is not None:
        svc._hold_timer.cancel()
        svc._hold_timer = None


def _quick_tap(svc):
    """Simulate a quick tap (press + release well under _HOLD_THRESHOLD)."""
    svc._on_dictate_key_press()
    time.sleep(0.05)
    svc._on_dictate_key_release()


# ---------------------------------------------------------------------------
# Double-tap → toggle (start recording)
# ---------------------------------------------------------------------------

class TestDoubleTap:
    def test_two_quick_taps_fire_toggle(self, svc):
        toggle = MagicMock()
        svc._on_dictate_toggle = toggle

        _quick_tap(svc)         # first tap
        time.sleep(0.05)
        _quick_tap(svc)         # second quick tap → fires toggle on release

        toggle.assert_called_once()

    def test_single_tap_does_not_fire_toggle(self, svc):
        toggle = MagicMock()
        svc._on_dictate_toggle = toggle

        _quick_tap(svc)

        toggle.assert_not_called()

    def test_second_tap_without_prior_release_is_ignored(self, svc):
        """Key repeat (press without prior release) must not count as second tap."""
        toggle = MagicMock()
        svc._on_dictate_toggle = toggle

        svc._on_dictate_key_press()
        time.sleep(0.02)
        svc._on_dictate_key_press()  # repeat while hold timer running → ignored

        toggle.assert_not_called()

    def test_triple_tap_fires_toggle_only_once(self, svc):
        """Second tap fires toggle; third tap starts a fresh first-tap cycle."""
        toggle = MagicMock()
        svc._on_dictate_toggle = toggle

        _quick_tap(svc)        # first tap
        time.sleep(0.05)
        _quick_tap(svc)        # second tap → fires toggle
        time.sleep(0.05)
        _quick_tap(svc)        # third tap = first tap of new cycle, no extra toggle

        assert toggle.call_count == 1

    def test_toggle_fires_on_release_not_press(self, svc):
        """Toggle should fire when the second tap is released, not when it's pressed."""
        toggle = MagicMock()
        svc._on_dictate_toggle = toggle

        _quick_tap(svc)                  # first tap
        time.sleep(0.05)
        svc._on_dictate_key_press()      # second press (hold timer starts)
        toggle.assert_not_called()       # not yet — still holding

        time.sleep(0.05)
        svc._on_dictate_key_release()    # quick release → fires toggle
        toggle.assert_called_once()


# ---------------------------------------------------------------------------
# Tap then hold → hold_start / hold_end
# ---------------------------------------------------------------------------

class TestHold:
    def test_tap_then_hold_fires_hold_start(self, svc):
        hold_start = MagicMock()
        svc._on_dictate_hold_start = hold_start

        _quick_tap(svc)                         # first tap
        time.sleep(0.05)
        svc._on_dictate_key_press()             # second press, then hold
        time.sleep(_HOLD_THRESHOLD + 0.05)      # hold threshold fires

        hold_start.assert_called_once()

    def test_tap_then_hold_release_fires_hold_end(self, svc):
        hold_end = MagicMock()
        svc._on_dictate_hold_end = hold_end

        _quick_tap(svc)
        time.sleep(0.05)
        svc._on_dictate_key_press()
        time.sleep(_HOLD_THRESHOLD + 0.05)
        svc._on_dictate_key_release()

        hold_end.assert_called_once()

    def test_tap_then_quick_release_does_not_fire_hold_end(self, svc):
        hold_end = MagicMock()
        svc._on_dictate_hold_end = hold_end

        _quick_tap(svc)
        time.sleep(0.05)
        _quick_tap(svc)   # second quick tap → toggle, NOT hold

        hold_end.assert_not_called()

    def test_long_first_press_alone_does_nothing(self, svc):
        """A single long press from idle should not start hold recording."""
        hold_start = MagicMock()
        svc._on_dictate_hold_start = hold_start

        svc._on_dictate_key_press()
        time.sleep(_HOLD_THRESHOLD + 0.05)

        hold_start.assert_not_called()

    def test_tap_then_hold_not_toggle(self, svc):
        toggle = MagicMock()
        hold_start = MagicMock()
        svc._on_dictate_toggle = toggle
        svc._on_dictate_hold_start = hold_start

        _quick_tap(svc)
        time.sleep(0.05)
        svc._on_dictate_key_press()
        time.sleep(_HOLD_THRESHOLD + 0.05)

        toggle.assert_not_called()
        hold_start.assert_called_once()

    def test_key_repeat_during_hold_recording_is_ignored(self, svc):
        hold_start = MagicMock()
        hold_end = MagicMock()
        svc._on_dictate_hold_start = hold_start
        svc._on_dictate_hold_end = hold_end

        _quick_tap(svc)
        time.sleep(0.05)
        svc._on_dictate_key_press()
        time.sleep(_HOLD_THRESHOLD + 0.05)  # hold_start fires
        svc._on_dictate_key_press()          # repeat → ignored
        svc._on_dictate_key_press()          # repeat → ignored
        svc._on_dictate_key_release()

        hold_start.assert_called_once()
        hold_end.assert_called_once()


# ---------------------------------------------------------------------------
# Toggle recording → press + release stops it
# ---------------------------------------------------------------------------

class TestToggleStop:
    def _svc_in_toggle_recording(self, svc):
        svc._get_is_toggle_recording = lambda: True
        return svc

    def test_press_while_toggle_recording_sets_expect_flag(self, svc):
        self._svc_in_toggle_recording(svc)
        svc._on_dictate_key_press()
        assert svc._expect_release_to_stop is True

    def test_release_after_toggle_stop_fires_single_release(self, svc):
        single_release = MagicMock()
        svc._on_dictate_single_release = single_release
        self._svc_in_toggle_recording(svc)

        svc._on_dictate_key_press()
        svc._on_dictate_key_release()

        single_release.assert_called_once()

    def test_toggle_stop_does_not_start_hold_timer(self, svc):
        self._svc_in_toggle_recording(svc)
        svc._on_dictate_key_press()
        assert svc._hold_timer is None

    def test_toggle_stop_does_not_fire_toggle_or_hold(self, svc):
        toggle = MagicMock()
        hold_end = MagicMock()
        svc._on_dictate_toggle = toggle
        svc._on_dictate_hold_end = hold_end
        self._svc_in_toggle_recording(svc)

        svc._on_dictate_key_press()
        svc._on_dictate_key_release()

        toggle.assert_not_called()
        hold_end.assert_not_called()

    def test_expect_flag_cleared_after_release(self, svc):
        self._svc_in_toggle_recording(svc)
        svc._on_dictate_key_press()
        svc._on_dictate_key_release()
        assert svc._expect_release_to_stop is False

    def test_key_repeat_during_toggle_stop_is_safe(self, svc):
        single_release = MagicMock()
        svc._on_dictate_single_release = single_release
        self._svc_in_toggle_recording(svc)

        svc._on_dictate_key_press()   # sets flag
        svc._on_dictate_key_press()   # repeat
        svc._on_dictate_key_release() # fires once

        single_release.assert_called_once()


# ---------------------------------------------------------------------------
# State reset between interactions
# ---------------------------------------------------------------------------

class TestStateReset:
    def test_tap_after_hold_session_starts_fresh(self, svc):
        """After a complete tap-then-hold session, next tap should start a fresh cycle."""
        toggle = MagicMock()
        svc._on_dictate_toggle = toggle

        # Complete tap-then-hold session
        _quick_tap(svc)
        time.sleep(0.05)
        svc._on_dictate_key_press()
        time.sleep(_HOLD_THRESHOLD + 0.05)
        svc._on_dictate_key_release()

        # Single tap afterwards → must NOT trigger toggle
        _quick_tap(svc)
        time.sleep(0.02)

        toggle.assert_not_called()

    def test_in_hold_recording_flag_reset_after_release(self, svc):
        _quick_tap(svc)
        time.sleep(0.05)
        svc._on_dictate_key_press()
        time.sleep(_HOLD_THRESHOLD + 0.05)
        assert svc._in_hold_recording is True
        svc._on_dictate_key_release()
        assert svc._in_hold_recording is False

    def test_after_first_tap_set_after_single_tap(self, svc):
        _quick_tap(svc)
        assert svc._after_first_tap is True

    def test_after_first_tap_cleared_after_double_tap(self, svc):
        _quick_tap(svc)
        time.sleep(0.05)
        _quick_tap(svc)
        assert svc._after_first_tap is False


# ---------------------------------------------------------------------------
# start / stop lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_start_registers_callbacks(self, svc):
        cb = MagicMock()
        with patch("threading.Thread.start"):
            svc.start(on_scribe=cb)
        assert svc._on_scribe is cb

    def test_start_registers_get_is_toggle_recording(self, svc):
        getter = lambda: True
        with patch("threading.Thread.start"):
            svc.start(get_is_toggle_recording=getter)
        assert svc._get_is_toggle_recording is getter

    def test_start_without_pynput_does_not_raise(self, svc):
        import liscribe.services.hotkey_service as hs_module
        original = hs_module._PYNPUT_AVAILABLE
        try:
            hs_module._PYNPUT_AVAILABLE = False
            svc.start()
        finally:
            hs_module._PYNPUT_AVAILABLE = original

    def test_stop_on_idle_is_safe(self, svc):
        svc.stop()
