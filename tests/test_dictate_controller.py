"""Tests for DictateController — Dictate workflow orchestration.

State machine: IDLE → (start) → RECORDING → (stop) → IDLE + background paste.
Permission gate, paste path, clipboard fallback, auto-enter, and error handling.

All tests use mocked services; no audio hardware, models, or UI required.
Tests are written before implementation (TDD red phase).
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, call, patch

import pytest

from liscribe.controllers.dictate_controller import (
    DictateController,
    DictateState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transcribe_result(text: str = "hello world") -> MagicMock:
    result = MagicMock()
    result.text = text
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def audio_svc():
    svc = MagicMock()
    svc.is_recording = False
    svc.get_levels.return_value = [0.5] * 30
    svc.stop.return_value = "/tmp/dictate.wav"
    svc.get_session_start_time.return_value = time.time() - 3.0
    return svc


@pytest.fixture()
def model_svc():
    svc = MagicMock()
    svc.is_downloaded.return_value = True
    svc.transcribe.return_value = _make_transcribe_result("hello world")
    return svc


@pytest.fixture()
def config_svc():
    svc = MagicMock()
    svc.dictation_model = "base"
    svc.dictation_auto_enter = False
    svc.default_mic = None
    return svc


@pytest.fixture()
def can_dictate_ok():
    return MagicMock(return_value=(True, []))


@pytest.fixture()
def can_dictate_fail():
    return MagicMock(return_value=(False, ["Accessibility"]))


@pytest.fixture()
def controller(audio_svc, model_svc, config_svc, can_dictate_ok):
    return DictateController(
        audio=audio_svc,
        model=model_svc,
        config=config_svc,
        can_dictate=can_dictate_ok,
    )


def _force_recording(
    ctrl: DictateController,
    hold: bool = False,
    target_bundle_id: str | None = None,
) -> None:
    """Put controller directly into RECORDING state without audio hardware."""
    ctrl._state = DictateState.RECORDING
    ctrl._is_hold_mode = hold
    ctrl._start_time = time.monotonic() - 2.0
    ctrl._target_bundle_id = target_bundle_id


def _wait_idle(ctrl: DictateController, timeout: float = 3.0) -> None:
    """Block until controller reaches IDLE and the background worker has finished."""
    deadline = time.monotonic() + timeout
    while ctrl.state != DictateState.IDLE:
        if time.monotonic() > deadline:
            raise TimeoutError("DictateController did not return to IDLE")
        time.sleep(0.05)
    # Join the worker thread so all side-effects (notify, paste) complete before asserting.
    if ctrl._last_worker is not None:
        ctrl._last_worker.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_state_is_idle(self, controller):
        assert controller.state == DictateState.IDLE

    def test_is_not_recording(self, controller):
        assert controller.is_recording is False


# ---------------------------------------------------------------------------
# handle_toggle() — start path
# ---------------------------------------------------------------------------


class TestHandleToggleStart:
    def test_starts_recording_when_idle(self, controller, audio_svc):
        controller.handle_toggle()
        audio_svc.start.assert_called_once()

    def test_state_is_recording_after_start(self, controller):
        controller.handle_toggle()
        assert controller.state == DictateState.RECORDING

    def test_returns_ok_true(self, controller):
        result = controller.handle_toggle()
        assert result["ok"] is True

    def test_is_not_hold_mode_after_toggle(self, controller):
        controller.handle_toggle()
        assert controller._is_hold_mode is False

    def test_start_time_set_after_toggle(self, controller):
        before = time.monotonic()
        controller.handle_toggle()
        assert controller._start_time is not None
        assert controller._start_time >= before

    def test_audio_start_called_with_default_mic(self, controller, audio_svc, config_svc):
        config_svc.default_mic = None
        controller.handle_toggle()
        audio_svc.start.assert_called_once_with(mic=None, speaker=False)

    def test_speaker_always_false(self, controller, audio_svc, config_svc):
        config_svc.default_mic = "USB Mic"
        controller.handle_toggle()
        _, kwargs = audio_svc.start.call_args
        assert kwargs.get("speaker") is False or audio_svc.start.call_args[1].get("speaker") is False


# ---------------------------------------------------------------------------
# handle_toggle() — stop path
# ---------------------------------------------------------------------------


class TestHandleToggleStop:
    def test_stop_returns_ok_true(self, controller):
        _force_recording(controller)
        result = controller.handle_toggle()
        assert result["ok"] is True

    def test_state_immediately_idle_on_toggle_stop(self, controller):
        _force_recording(controller)
        controller.handle_toggle()
        assert controller.state == DictateState.IDLE

    def test_audio_stop_called(self, controller, audio_svc):
        _force_recording(controller)
        controller.handle_toggle()
        _wait_idle(controller)
        audio_svc.stop.assert_called_once()

    def test_model_transcribe_called_with_wav_path(self, controller, audio_svc, model_svc):
        audio_svc.stop.return_value = "/tmp/dictate.wav"
        _force_recording(controller)
        controller.handle_toggle()
        _wait_idle(controller)
        model_svc.transcribe.assert_called_once()
        args, kwargs = model_svc.transcribe.call_args
        assert str(args[0]) == "/tmp/dictate.wav" or kwargs.get("wav_path") == "/tmp/dictate.wav"

    def test_transcribe_uses_dictation_model(self, controller, model_svc, config_svc):
        config_svc.dictation_model = "tiny"
        _force_recording(controller)
        controller.handle_toggle()
        _wait_idle(controller)
        _, kwargs = model_svc.transcribe.call_args
        assert kwargs.get("model_size") == "tiny"

    def test_clipboard_set_with_transcribed_text(self, controller, model_svc):
        model_svc.transcribe.return_value = _make_transcribe_result("transcribed text")
        _force_recording(controller, target_bundle_id=None)
        with patch("pyperclip.copy") as mock_copy:
            controller.handle_toggle()
            _wait_idle(controller)
        mock_copy.assert_called_once_with("transcribed text")

    def test_toggle_hold_mode_recording_is_ignored(self, controller):
        """handle_toggle() while in hold mode should be a no-op (stop is via hold_end)."""
        _force_recording(controller, hold=True)
        result = controller.handle_toggle()
        # Returns ok but does not stop
        assert result["ok"] is True
        assert controller.state == DictateState.RECORDING


# ---------------------------------------------------------------------------
# handle_hold_start()
# ---------------------------------------------------------------------------


class TestHandleHoldStart:
    def test_starts_recording(self, controller, audio_svc):
        controller.handle_hold_start()
        audio_svc.start.assert_called_once()

    def test_state_is_recording(self, controller):
        controller.handle_hold_start()
        assert controller.state == DictateState.RECORDING

    def test_is_hold_mode_true(self, controller):
        controller.handle_hold_start()
        assert controller._is_hold_mode is True

    def test_returns_ok_true(self, controller):
        result = controller.handle_hold_start()
        assert result["ok"] is True

    def test_no_op_when_already_recording(self, controller, audio_svc):
        _force_recording(controller)
        controller.handle_hold_start()
        audio_svc.start.assert_not_called()


# ---------------------------------------------------------------------------
# handle_hold_end()
# ---------------------------------------------------------------------------


class TestHandleHoldEnd:
    def test_returns_ok_true(self, controller):
        _force_recording(controller, hold=True)
        result = controller.handle_hold_end()
        assert result["ok"] is True

    def test_state_immediately_idle(self, controller):
        _force_recording(controller, hold=True)
        controller.handle_hold_end()
        assert controller.state == DictateState.IDLE

    def test_audio_stop_called(self, controller, audio_svc):
        _force_recording(controller, hold=True)
        controller.handle_hold_end()
        _wait_idle(controller)
        audio_svc.stop.assert_called_once()

    def test_ignored_when_not_in_hold_mode(self, controller, audio_svc):
        """hold_end while in toggle mode should not stop."""
        _force_recording(controller, hold=False)
        controller.handle_hold_end()
        # State must not change and audio.stop must not be called
        assert controller.state == DictateState.RECORDING
        audio_svc.stop.assert_not_called()

    def test_ignored_when_idle(self, controller, audio_svc):
        controller.handle_hold_end()
        audio_svc.stop.assert_not_called()
        assert controller.state == DictateState.IDLE


# ---------------------------------------------------------------------------
# Permission gate
# ---------------------------------------------------------------------------


class TestPermissionGate:
    def test_missing_permissions_prevent_recording(self, audio_svc, model_svc, config_svc, can_dictate_fail):
        ctrl = DictateController(
            audio=audio_svc,
            model=model_svc,
            config=config_svc,
            can_dictate=can_dictate_fail,
        )
        ctrl.handle_toggle()
        audio_svc.start.assert_not_called()

    def test_missing_permissions_returns_error(self, audio_svc, model_svc, config_svc, can_dictate_fail):
        ctrl = DictateController(
            audio=audio_svc,
            model=model_svc,
            config=config_svc,
            can_dictate=can_dictate_fail,
        )
        result = ctrl.handle_toggle()
        assert result["ok"] is False
        assert result.get("error") == "setup_required"

    def test_missing_permissions_lists_names(self, audio_svc, model_svc, config_svc, can_dictate_fail):
        ctrl = DictateController(
            audio=audio_svc,
            model=model_svc,
            config=config_svc,
            can_dictate=can_dictate_fail,
        )
        result = ctrl.handle_toggle()
        assert "Accessibility" in result.get("missing_permissions", [])

    def test_state_stays_idle_on_permission_failure(self, audio_svc, model_svc, config_svc, can_dictate_fail):
        ctrl = DictateController(
            audio=audio_svc,
            model=model_svc,
            config=config_svc,
            can_dictate=can_dictate_fail,
        )
        ctrl.handle_toggle()
        assert ctrl.state == DictateState.IDLE

    def test_hold_start_also_checks_permissions(self, audio_svc, model_svc, config_svc, can_dictate_fail):
        ctrl = DictateController(
            audio=audio_svc,
            model=model_svc,
            config=config_svc,
            can_dictate=can_dictate_fail,
        )
        result = ctrl.handle_hold_start()
        assert result["ok"] is False
        audio_svc.start.assert_not_called()

    def test_permission_checked_on_every_trigger(self, audio_svc, model_svc, config_svc):
        """Granting permission should let the next trigger work without restart."""
        call_count = 0
        call_results = [(False, ["Accessibility"]), (True, [])]

        def can_dictate_dynamic():
            nonlocal call_count
            result = call_results[min(call_count, len(call_results) - 1)]
            call_count += 1
            return result

        ctrl = DictateController(
            audio=audio_svc,
            model=model_svc,
            config=config_svc,
            can_dictate=can_dictate_dynamic,
        )
        first = ctrl.handle_toggle()
        assert first["ok"] is False  # first attempt fails
        second = ctrl.handle_toggle()
        assert second["ok"] is True  # permission granted, second attempt works
        audio_svc.start.assert_called_once()


# ---------------------------------------------------------------------------
# No model downloaded
# ---------------------------------------------------------------------------


class TestNoModel:
    def test_no_model_prevents_recording(self, audio_svc, model_svc, config_svc, can_dictate_ok):
        model_svc.is_downloaded.return_value = False
        ctrl = DictateController(
            audio=audio_svc,
            model=model_svc,
            config=config_svc,
            can_dictate=can_dictate_ok,
        )
        ctrl.handle_toggle()
        audio_svc.start.assert_not_called()

    def test_no_model_returns_error(self, audio_svc, model_svc, config_svc, can_dictate_ok):
        model_svc.is_downloaded.return_value = False
        ctrl = DictateController(
            audio=audio_svc,
            model=model_svc,
            config=config_svc,
            can_dictate=can_dictate_ok,
        )
        result = ctrl.handle_toggle()
        assert result["ok"] is False
        assert result.get("error") == "no_model"

    def test_no_model_state_stays_idle(self, audio_svc, model_svc, config_svc, can_dictate_ok):
        model_svc.is_downloaded.return_value = False
        ctrl = DictateController(
            audio=audio_svc,
            model=model_svc,
            config=config_svc,
            can_dictate=can_dictate_ok,
        )
        ctrl.handle_toggle()
        assert ctrl.state == DictateState.IDLE


# ---------------------------------------------------------------------------
# Paste path — external focus (normal flow)
# ---------------------------------------------------------------------------


class TestPasteWithFocus:
    def test_paste_cmd_v_simulated_when_focus_present(self, controller, model_svc, audio_svc):
        model_svc.transcribe.return_value = _make_transcribe_result("paste this")
        _force_recording(controller, target_bundle_id="com.apple.TextEdit")
        with patch("pyperclip.copy"):
            with patch("liscribe.controllers.dictate_controller._activate_bundle"):
                with patch(
                    "liscribe.controllers.dictate_controller._simulate_paste"
                ) as mock_paste:
                    controller.handle_toggle()
                    _wait_idle(controller)
        mock_paste.assert_called_once()

    def test_auto_enter_true_simulates_return(self, controller, model_svc, config_svc, audio_svc):
        config_svc.dictation_auto_enter = True
        model_svc.transcribe.return_value = _make_transcribe_result("type this")
        _force_recording(controller, target_bundle_id="com.apple.TextEdit")
        with patch("pyperclip.copy"):
            with patch("liscribe.controllers.dictate_controller._activate_bundle"):
                with patch(
                    "liscribe.controllers.dictate_controller._simulate_paste"
                ):
                    with patch(
                        "liscribe.controllers.dictate_controller._simulate_enter"
                    ) as mock_enter:
                        controller.handle_toggle()
                        _wait_idle(controller)
        mock_enter.assert_called_once()

    def test_auto_enter_false_does_not_simulate_return(
        self, controller, model_svc, config_svc, audio_svc
    ):
        config_svc.dictation_auto_enter = False
        model_svc.transcribe.return_value = _make_transcribe_result("type this")
        _force_recording(controller, target_bundle_id="com.apple.TextEdit")
        with patch("pyperclip.copy"):
            with patch("liscribe.controllers.dictate_controller._activate_bundle"):
                with patch("liscribe.controllers.dictate_controller._simulate_paste"):
                    with patch(
                        "liscribe.controllers.dictate_controller._simulate_enter"
                    ) as mock_enter:
                        controller.handle_toggle()
                        _wait_idle(controller)
        mock_enter.assert_not_called()


# ---------------------------------------------------------------------------
# Clipboard fallback — no external focus
# ---------------------------------------------------------------------------


class TestClipboardFallback:
    def test_clipboard_set_even_without_focus(self, controller, model_svc, audio_svc):
        model_svc.transcribe.return_value = _make_transcribe_result("fallback text")
        _force_recording(controller, target_bundle_id=None)
        with patch("pyperclip.copy") as mock_copy:
            with patch("liscribe.controllers.dictate_controller._simulate_paste") as mock_paste:
                controller.handle_toggle()
                _wait_idle(controller)
        mock_copy.assert_called_once_with("fallback text")
        mock_paste.assert_not_called()

    def test_notification_shown_when_no_focus(self, controller, model_svc, audio_svc):
        model_svc.transcribe.return_value = _make_transcribe_result("fallback text")
        _force_recording(controller, target_bundle_id=None)
        with patch("pyperclip.copy"):
            with patch(
                "liscribe.controllers.dictate_controller._notify"
            ) as mock_notify:
                controller.handle_toggle()
                _wait_idle(controller)
        mock_notify.assert_called_once()


# ---------------------------------------------------------------------------
# Error handling — no silent failures
# ---------------------------------------------------------------------------


class TestErrors:
    def test_transcription_failure_does_not_crash(self, controller, model_svc, audio_svc):
        model_svc.transcribe.side_effect = RuntimeError("model exploded")
        _force_recording(controller)
        with patch("liscribe.controllers.dictate_controller._notify"):
            controller.handle_toggle()
            _wait_idle(controller)
        # State must be IDLE — controller recovered cleanly

    def test_transcription_failure_notifies_user(self, controller, model_svc, audio_svc):
        model_svc.transcribe.side_effect = RuntimeError("model exploded")
        _force_recording(controller)
        with patch(
            "liscribe.controllers.dictate_controller._notify"
        ) as mock_notify:
            controller.handle_toggle()
            _wait_idle(controller)
        mock_notify.assert_called_once()

    def test_empty_transcription_result_does_not_paste(self, controller, model_svc):
        model_svc.transcribe.return_value = _make_transcribe_result("   ")
        _force_recording(controller)
        with patch("pyperclip.copy") as mock_copy:
            with patch("liscribe.controllers.dictate_controller._simulate_paste") as mock_paste:
                controller.handle_toggle()
                _wait_idle(controller)
        mock_copy.assert_not_called()
        mock_paste.assert_not_called()

    def test_audio_start_failure_returns_error(
        self, audio_svc, model_svc, config_svc, can_dictate_ok
    ):
        audio_svc.start.side_effect = RuntimeError("mic unavailable")
        ctrl = DictateController(
            audio=audio_svc,
            model=model_svc,
            config=config_svc,
            can_dictate=can_dictate_ok,
        )
        result = ctrl.handle_toggle()
        assert result["ok"] is False

    def test_audio_start_failure_state_stays_idle(
        self, audio_svc, model_svc, config_svc, can_dictate_ok
    ):
        audio_svc.start.side_effect = RuntimeError("mic unavailable")
        ctrl = DictateController(
            audio=audio_svc,
            model=model_svc,
            config=config_svc,
            can_dictate=can_dictate_ok,
        )
        ctrl.handle_toggle()
        assert ctrl.state == DictateState.IDLE


# ---------------------------------------------------------------------------
# get_waveform() / get_elapsed()
# ---------------------------------------------------------------------------


class TestRealtimeData:
    def test_get_waveform_delegates_to_audio(self, controller, audio_svc):
        audio_svc.get_levels.return_value = [0.1, 0.2, 0.3]
        result = controller.get_waveform(bars=3)
        audio_svc.get_levels.assert_called_once_with(bars=3)
        assert result == [0.1, 0.2, 0.3]

    def test_get_waveform_returns_empty_when_idle(self, controller, audio_svc):
        audio_svc.get_levels.return_value = []
        result = controller.get_waveform()
        assert isinstance(result, list)

    def test_get_elapsed_returns_zero_when_idle(self, controller):
        assert controller.get_elapsed() == 0.0

    def test_get_elapsed_returns_positive_when_recording(self, controller):
        _force_recording(controller)
        elapsed = controller.get_elapsed()
        assert elapsed >= 0.0

    def test_get_elapsed_uses_start_time(self, controller):
        _force_recording(controller)
        controller._start_time = time.monotonic() - 7.0
        elapsed = controller.get_elapsed()
        assert 6.0 <= elapsed <= 8.5
