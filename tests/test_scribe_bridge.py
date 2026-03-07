"""Tests for ScribeBridge — JS-to-Python call translation layer.

Bridge methods must:
  - Delegate to controller/services — no business logic here
  - Return JSON-serialisable dicts
  - Surface errors to the caller rather than silently swallowing them

All tests use mocked controller and services.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from liscribe.bridge.scribe_bridge import ScribeBridge
from liscribe.controllers.scribe_controller import ControllerState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def controller():
    ctrl = MagicMock()
    ctrl.state = ControllerState.RECORDING
    ctrl.is_recording = True
    ctrl.is_using_fallback_mic = False
    ctrl.selected_models = ["base"]
    ctrl.save_path = "~/transcripts"
    ctrl.get_waveform.return_value = [0.5] * 30
    ctrl.get_elapsed_seconds.return_value = 5.0
    ctrl.get_transcription_progress.return_value = []
    ctrl.add_note.return_value = MagicMock(index=1, text="test", timestamp=1.0)
    return ctrl


@pytest.fixture()
def model_svc():
    svc = MagicMock()
    svc.list_models.return_value = [
        {"name": "base", "is_downloaded": True, "size_label": "~145 MB"},
        {"name": "small", "is_downloaded": False, "size_label": "~465 MB"},
    ]
    return svc


@pytest.fixture()
def audio_svc():
    svc = MagicMock()
    svc.list_mics.return_value = [
        {"name": "MacBook Pro Mic", "index": 0, "is_default": True},
    ]
    return svc


@pytest.fixture()
def bridge(controller, model_svc, audio_svc):
    return ScribeBridge(controller=controller, model=model_svc, audio=audio_svc)


# ---------------------------------------------------------------------------
# get_mics()
# ---------------------------------------------------------------------------


class TestGetMics:
    def test_delegates_to_audio_list_mics(self, bridge, audio_svc):
        bridge.get_mics()
        audio_svc.list_mics.assert_called_once()

    def test_returns_list(self, bridge):
        result = bridge.get_mics()
        assert isinstance(result, list)

    def test_adds_fallback_flag_to_each_entry(self, bridge):
        result = bridge.get_mics()
        for entry in result:
            assert "is_fallback_active" in entry


# ---------------------------------------------------------------------------
# get_models()
# ---------------------------------------------------------------------------


class TestGetModels:
    def test_delegates_to_model_list_models(self, bridge, model_svc):
        bridge.get_models()
        model_svc.list_models.assert_called_once()

    def test_returns_list(self, bridge):
        result = bridge.get_models()
        assert isinstance(result, list)

    def test_adds_is_selected_flag(self, bridge, controller):
        controller.selected_models = ["base"]
        result = bridge.get_models()
        for entry in result:
            if entry["name"] == "base":
                assert entry["is_selected"] is True
            else:
                assert entry["is_selected"] is False


# ---------------------------------------------------------------------------
# get_save_path()
# ---------------------------------------------------------------------------


class TestGetSavePath:
    def test_returns_string(self, bridge):
        result = bridge.get_save_path()
        assert isinstance(result, str)

    def test_returns_controller_save_path(self, bridge, controller):
        controller.save_path = "/custom/path"
        result = bridge.get_save_path()
        assert result == "/custom/path"


# ---------------------------------------------------------------------------
# set_save_path()
# ---------------------------------------------------------------------------


class TestSetSavePath:
    def test_calls_controller_set_save_path(self, bridge, controller):
        bridge.set_save_path("/tmp/custom")
        controller.set_save_path.assert_called_once_with("/tmp/custom")


# ---------------------------------------------------------------------------
# set_mic()
# ---------------------------------------------------------------------------


class TestSetMic:
    def test_calls_controller_set_mic(self, bridge, controller):
        bridge.set_mic("USB Mic")
        controller.set_mic.assert_called_once_with("USB Mic")

    def test_also_calls_switch_mic_when_recording(self, bridge, controller):
        controller.is_recording = True
        bridge.set_mic("USB Mic")
        controller.switch_mic.assert_called_once_with("USB Mic")

    def test_does_not_call_switch_mic_when_idle(self, bridge, controller):
        controller.is_recording = False
        bridge.set_mic("USB Mic")
        controller.switch_mic.assert_not_called()


# ---------------------------------------------------------------------------
# toggle_speaker()
# ---------------------------------------------------------------------------


class TestToggleSpeaker:
    def test_calls_controller_set_speaker(self, bridge, controller):
        controller.set_speaker.return_value = None
        bridge.toggle_speaker(True)
        controller.set_speaker.assert_called_once_with(True)

    def test_returns_ok_true_on_success(self, bridge, controller):
        controller.set_speaker.return_value = None
        result = bridge.toggle_speaker(True)
        assert result["ok"] is True

    def test_returns_ok_false_with_error_on_failure(self, bridge, controller):
        controller.set_speaker.return_value = "BlackHole not found"
        result = bridge.toggle_speaker(True)
        assert result["ok"] is False
        assert "BlackHole" in result["error"]


# ---------------------------------------------------------------------------
# toggle_model()
# ---------------------------------------------------------------------------


class TestToggleModel:
    def test_selecting_model_adds_to_selection(self, bridge, controller):
        controller.selected_models = []
        bridge.toggle_model("small", True)
        controller.set_models.assert_called_once()
        # verify "small" is in the passed list
        new_models = controller.set_models.call_args[0][0]
        assert "small" in new_models

    def test_deselecting_model_removes_from_selection(self, bridge, controller):
        controller.selected_models = ["base", "small"]
        bridge.toggle_model("small", False)
        controller.set_models.assert_called_once()
        new_models = controller.set_models.call_args[0][0]
        assert "small" not in new_models

    def test_deselecting_missing_model_is_safe(self, bridge, controller):
        controller.selected_models = ["base"]
        bridge.toggle_model("large", False)  # not in list, must not raise


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


# ---------------------------------------------------------------------------
# get_elapsed()
# ---------------------------------------------------------------------------


class TestGetElapsed:
    def test_delegates_to_controller(self, bridge, controller):
        bridge.get_elapsed()
        controller.get_elapsed_seconds.assert_called_once()

    def test_returns_float(self, bridge):
        result = bridge.get_elapsed()
        assert isinstance(result, float)


# ---------------------------------------------------------------------------
# add_note()
# ---------------------------------------------------------------------------


class TestAddNote:
    def test_calls_controller_add_note(self, bridge, controller):
        bridge.add_note("my note")
        controller.add_note.assert_called_once_with("my note")

    def test_returns_dict(self, bridge):
        result = bridge.add_note("my note")
        assert isinstance(result, dict)

    def test_returns_ok_true_on_success(self, bridge):
        result = bridge.add_note("my note")
        assert result["ok"] is True

    def test_returns_ok_false_on_error(self, bridge, controller):
        controller.add_note.side_effect = RuntimeError("not recording")
        result = bridge.add_note("my note")
        assert result["ok"] is False
        assert "error" in result


# ---------------------------------------------------------------------------
# cancel()
# ---------------------------------------------------------------------------


class TestCancel:
    def test_calls_controller_cancel(self, bridge, controller):
        bridge.cancel()
        controller.cancel.assert_called_once()

    def test_returns_dict(self, bridge):
        result = bridge.cancel()
        assert isinstance(result, dict)

    def test_returns_ok_true(self, bridge):
        result = bridge.cancel()
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# stop_and_save()
# ---------------------------------------------------------------------------


class TestStopAndSave:
    def test_calls_controller_stop_and_save(self, bridge, controller):
        mock_result = MagicMock()
        mock_result.is_no_model_mode = False
        mock_result.wav_path = "/tmp/x.wav"
        mock_result.transcripts = []
        mock_result.save_folder = "~/transcripts"
        controller.stop_and_save.return_value = mock_result
        bridge.stop_and_save()
        controller.stop_and_save.assert_called_once()

    def test_returns_dict(self, bridge, controller):
        mock_result = MagicMock()
        mock_result.is_no_model_mode = False
        mock_result.wav_path = "/tmp/x.wav"
        mock_result.transcripts = []
        mock_result.save_folder = "~/transcripts"
        controller.stop_and_save.return_value = mock_result
        result = bridge.stop_and_save()
        assert isinstance(result, dict)

    def test_no_model_mode_in_result(self, bridge, controller):
        mock_result = MagicMock()
        mock_result.is_no_model_mode = True
        mock_result.wav_path = "/tmp/x.wav"
        mock_result.transcripts = []
        mock_result.save_folder = "~/transcripts"
        controller.stop_and_save.return_value = mock_result
        result = bridge.stop_and_save()
        assert result["is_no_model_mode"] is True

    def test_wav_path_in_result(self, bridge, controller):
        mock_result = MagicMock()
        mock_result.is_no_model_mode = False
        mock_result.wav_path = "/tmp/session.wav"
        mock_result.transcripts = []
        mock_result.save_folder = "~/transcripts"
        controller.stop_and_save.return_value = mock_result
        result = bridge.stop_and_save()
        assert result["wav_path"] == "/tmp/session.wav"

    def test_returns_error_dict_on_failure(self, bridge, controller):
        controller.stop_and_save.side_effect = RuntimeError("not recording")
        result = bridge.stop_and_save()
        assert result.get("ok") is False
        assert "error" in result


# ---------------------------------------------------------------------------
# get_state()
# ---------------------------------------------------------------------------


class TestGetState:
    def test_returns_dict(self, bridge):
        result = bridge.get_state()
        assert isinstance(result, dict)

    def test_includes_state_field(self, bridge, controller):
        controller.state = ControllerState.RECORDING
        result = bridge.get_state()
        assert "state" in result

    def test_includes_is_using_fallback_mic(self, bridge, controller):
        controller.is_using_fallback_mic = True
        result = bridge.get_state()
        assert result["is_using_fallback_mic"] is True

    def test_includes_save_path(self, bridge, controller):
        controller.save_path = "/tmp/out"
        result = bridge.get_state()
        assert result["save_path"] == "/tmp/out"


# ---------------------------------------------------------------------------
# get_transcription_progress()
# ---------------------------------------------------------------------------


class TestGetTranscriptionProgress:
    def test_delegates_to_controller(self, bridge, controller):
        bridge.get_transcription_progress()
        controller.get_transcription_progress.assert_called_once()

    def test_returns_list(self, bridge):
        result = bridge.get_transcription_progress()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# open_in_transcribe() — Phase 5: wire to Transcribe panel with prefill
# ---------------------------------------------------------------------------


class TestOpenInTranscribe:
    def test_calls_callback_with_wav_path_when_provided(self):
        app_actions = MagicMock()
        ctrl = MagicMock()
        bridge = ScribeBridge(
            controller=ctrl,
            model=MagicMock(),
            audio=MagicMock(),
            app_actions=app_actions,
        )
        bridge.open_in_transcribe("/tmp/recording.wav")
        app_actions.open_in_transcribe.assert_called_once_with("/tmp/recording.wav", None)

    def test_callback_receives_save_folder_when_passed(self):
        app_actions = MagicMock()
        bridge = ScribeBridge(
            controller=MagicMock(),
            model=MagicMock(),
            audio=MagicMock(),
            app_actions=app_actions,
        )
        bridge.open_in_transcribe("/tmp/recording.wav", save_folder="/out")
        app_actions.open_in_transcribe.assert_called_once_with("/tmp/recording.wav", "/out")


class TestOpenTranscript:
    def test_delegates_to_controller(self, bridge, controller):
        bridge.open_transcript("/tmp/out_base.md")
        controller.open_transcript.assert_called_once_with("/tmp/out_base.md")
