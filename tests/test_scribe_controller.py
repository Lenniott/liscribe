"""Tests for ScribeController — Scribe workflow orchestration.

All tests use mocked services; no audio hardware or models are required.
Tests are written before implementation (TDD red phase).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from liscribe.controllers.scribe_controller import (
    ControllerState,
    ModelProgress,
    ScribeController,
    ScribeResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def audio_svc():
    svc = MagicMock()
    svc.is_recording = False
    svc.get_levels.return_value = [0.5] * 30
    svc.stop.return_value = "/tmp/session.wav"
    svc.preferred_mic_index.return_value = 0
    svc.get_session_start_time.return_value = time.time() - 5.0
    return svc


@pytest.fixture()
def model_svc():
    svc = MagicMock()
    svc.list_models.return_value = [
        {"name": "base", "is_downloaded": True, "size_label": "~145 MB"},
    ]
    svc.is_downloaded.return_value = True
    svc.transcribe.return_value = MagicMock()
    svc.save_transcript.return_value = Path("/tmp/session_base.md")
    svc.cleanup_wav.return_value = True
    return svc


@pytest.fixture()
def config_svc():
    svc = MagicMock()
    svc.save_folder = "~/transcripts"
    svc.keep_wav = True
    svc.scribe_models = ["base"]
    svc.default_mic = None
    return svc


@pytest.fixture()
def controller(audio_svc, model_svc, config_svc):
    return ScribeController(audio=audio_svc, model=model_svc, config=config_svc)


def _force_recording(controller: ScribeController) -> None:
    """Bypass audio hardware: put controller directly into RECORDING state."""
    controller._state = ControllerState.RECORDING
    controller._notes.start()


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_state_is_idle(self, controller):
        assert controller.state == ControllerState.IDLE

    def test_is_recording_false(self, controller):
        assert controller.is_recording is False

    def test_is_transcribing_false(self, controller):
        assert controller.is_transcribing is False

    def test_is_using_fallback_mic_false(self, controller):
        assert controller.is_using_fallback_mic is False

    def test_save_path_defaults_to_config(self, controller, config_svc):
        assert controller.save_path == config_svc.save_folder

    def test_selected_models_from_config(self, controller):
        assert controller.selected_models == ["base"]


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------


class TestStart:
    def test_transitions_to_recording(self, controller, audio_svc):
        controller.start()
        assert controller.state == ControllerState.RECORDING

    def test_calls_audio_start(self, controller, audio_svc):
        controller.start()
        audio_svc.start.assert_called_once()

    def test_passes_mic_name_to_audio(self, controller, audio_svc):
        controller.set_mic("USB Mic")
        controller.start()
        _, kwargs = audio_svc.start.call_args
        assert kwargs.get("mic") == "USB Mic" or audio_svc.start.call_args[0][0] == "USB Mic"

    def test_raises_if_already_recording(self, controller):
        _force_recording(controller)
        with pytest.raises(RuntimeError):
            controller.start()

    def test_raises_if_transcribing(self, controller):
        controller._state = ControllerState.TRANSCRIBING
        with pytest.raises(RuntimeError):
            controller.start()

    def test_fallback_flag_set_when_preferred_mic_unavailable(
        self, controller, audio_svc, config_svc
    ):
        config_svc.default_mic = "My USB Mic"
        audio_svc.preferred_mic_index.return_value = None
        controller.start()
        assert controller.is_using_fallback_mic is True

    def test_fallback_flag_clear_when_preferred_mic_available(
        self, controller, audio_svc, config_svc
    ):
        config_svc.default_mic = "My USB Mic"
        audio_svc.preferred_mic_index.return_value = 2
        controller.start()
        assert controller.is_using_fallback_mic is False

    def test_fallback_flag_clear_when_no_preference_set(
        self, controller, audio_svc, config_svc
    ):
        config_svc.default_mic = None
        controller.start()
        assert controller.is_using_fallback_mic is False


# ---------------------------------------------------------------------------
# cancel()
# ---------------------------------------------------------------------------


class TestCancel:
    def test_when_idle_does_not_raise(self, controller):
        controller.cancel()  # must not raise

    def test_calls_audio_cancel_when_recording(self, controller, audio_svc):
        _force_recording(controller)
        controller.cancel()
        audio_svc.cancel.assert_called_once()

    def test_resets_state_to_idle(self, controller, audio_svc):
        _force_recording(controller)
        controller.cancel()
        assert controller.state == ControllerState.IDLE

    def test_clears_notes(self, controller):
        _force_recording(controller)
        controller.add_note("a note")
        controller.cancel()
        # After cancel, a fresh start should not carry old notes
        controller.start()
        assert controller._notes.notes == []

    def test_does_not_call_audio_cancel_when_idle(self, controller, audio_svc):
        controller.cancel()
        audio_svc.cancel.assert_not_called()

    def test_cancel_during_transcribing_sets_cancelled_flag(self, controller):
        controller._state = ControllerState.TRANSCRIBING
        controller.cancel()
        assert controller._cancelled is True

    def test_cancel_during_transcribing_state_returns_to_idle(self, controller):
        controller._state = ControllerState.TRANSCRIBING
        controller.cancel()
        assert controller.state == ControllerState.IDLE


# ---------------------------------------------------------------------------
# Reuse after full cycle
# ---------------------------------------------------------------------------


class TestReuseAfterFullCycle:
    def test_controller_reusable_after_done_cycle(
        self, controller, audio_svc, model_svc
    ):
        model_svc.is_downloaded.return_value = False
        _force_recording(controller)
        controller.stop_and_save()
        assert controller.state == ControllerState.DONE
        controller.cancel()
        assert controller.state == ControllerState.IDLE
        controller.start()
        assert controller.state == ControllerState.RECORDING


# ---------------------------------------------------------------------------
# add_note()
# ---------------------------------------------------------------------------


class TestAddNote:
    def test_returns_note_with_correct_text(self, controller):
        _force_recording(controller)
        note = controller.add_note("important point")
        assert note.text == "important point"

    def test_returns_note_with_index_1_first(self, controller):
        _force_recording(controller)
        note = controller.add_note("first")
        assert note.index == 1

    def test_sequential_notes_have_ascending_indices(self, controller):
        _force_recording(controller)
        n1 = controller.add_note("one")
        n2 = controller.add_note("two")
        assert n2.index == n1.index + 1

    def test_raises_when_not_recording(self, controller):
        with pytest.raises(RuntimeError):
            controller.add_note("should fail")

    def test_raises_when_transcribing(self, controller):
        controller._state = ControllerState.TRANSCRIBING
        with pytest.raises(RuntimeError):
            controller.add_note("should fail")

    def test_empty_string_note_accepted(self, controller):
        _force_recording(controller)
        note = controller.add_note("")
        assert note.text == ""


# ---------------------------------------------------------------------------
# get_waveform()
# ---------------------------------------------------------------------------


class TestGetWaveform:
    def test_delegates_to_audio_get_levels(self, controller, audio_svc):
        result = controller.get_waveform()
        audio_svc.get_levels.assert_called_once()

    def test_returns_list(self, controller):
        assert isinstance(controller.get_waveform(), list)

    def test_returns_audio_service_values(self, controller, audio_svc):
        audio_svc.get_levels.return_value = [0.1, 0.2, 0.3]
        assert controller.get_waveform() == [0.1, 0.2, 0.3]


# ---------------------------------------------------------------------------
# get_elapsed_seconds()
# ---------------------------------------------------------------------------


class TestGetElapsed:
    def test_returns_zero_when_idle(self, controller):
        assert controller.get_elapsed_seconds() == 0.0

    def test_returns_positive_when_recording(self, controller, audio_svc):
        audio_svc.get_session_start_time.return_value = time.time() - 10.0
        controller._state = ControllerState.RECORDING
        elapsed = controller.get_elapsed_seconds()
        assert 9.0 <= elapsed <= 11.0

    def test_returns_zero_when_start_time_unknown(self, controller, audio_svc):
        audio_svc.get_session_start_time.return_value = None
        controller._state = ControllerState.RECORDING
        assert controller.get_elapsed_seconds() == 0.0


# ---------------------------------------------------------------------------
# set_mic() / set_speaker() / set_save_path() / set_models()
# ---------------------------------------------------------------------------


class TestSessionConfig:
    def test_set_mic_stores_name(self, controller):
        controller.set_mic("MacBook Pro Mic")
        assert controller._current_mic == "MacBook Pro Mic"

    def test_set_mic_none_clears_preference(self, controller):
        controller.set_mic("USB Mic")
        controller.set_mic(None)
        assert controller._current_mic is None

    def test_set_save_path_overrides_config(self, controller):
        controller.set_save_path("/tmp/custom")
        assert controller.save_path == "/tmp/custom"

    def test_set_save_path_empty_string_clears_override(self, controller, config_svc):
        controller.set_save_path("/tmp/custom")
        controller.set_save_path("")
        assert controller.save_path == config_svc.save_folder

    def test_set_models_updates_selection(self, controller):
        controller.set_models(["base", "small"])
        assert controller.selected_models == ["base", "small"]

    def test_set_models_empty_allowed(self, controller):
        controller.set_models([])
        assert controller.selected_models == []

    def test_set_speaker_during_recording_calls_enable(
        self, controller, audio_svc
    ):
        _force_recording(controller)
        audio_svc.enable_speaker_capture.return_value = None
        err = controller.set_speaker(True)
        audio_svc.enable_speaker_capture.assert_called_once()
        assert err is None

    def test_set_speaker_false_during_recording_calls_disable(
        self, controller, audio_svc
    ):
        _force_recording(controller)
        controller._speaker_enabled = True
        controller.set_speaker(False)
        audio_svc.disable_speaker_capture.assert_called_once()

    def test_set_speaker_when_idle_stores_flag(self, controller, audio_svc):
        controller.set_speaker(True)
        audio_svc.enable_speaker_capture.assert_not_called()
        assert controller._speaker_enabled is True

    def test_set_speaker_returns_error_from_audio(self, controller, audio_svc):
        _force_recording(controller)
        audio_svc.enable_speaker_capture.return_value = "BlackHole not found"
        err = controller.set_speaker(True)
        assert err == "BlackHole not found"

    def test_switch_mic_mid_recording_calls_audio(self, controller, audio_svc):
        _force_recording(controller)
        controller.switch_mic("USB Mic")
        audio_svc.switch_mic.assert_called_once_with("USB Mic")

    def test_switch_mic_not_recording_does_not_call_audio(
        self, controller, audio_svc
    ):
        controller.switch_mic("USB Mic")
        audio_svc.switch_mic.assert_not_called()


# ---------------------------------------------------------------------------
# stop_and_save() — no-model graceful degradation
# ---------------------------------------------------------------------------


class TestStopAndSaveNoModel:
    def test_returns_no_model_mode_true(self, controller, audio_svc, model_svc):
        model_svc.is_downloaded.return_value = False
        controller.set_models(["base"])
        _force_recording(controller)
        result = controller.stop_and_save()
        assert result.is_no_model_mode is True

    def test_returns_wav_path(self, controller, audio_svc, model_svc):
        model_svc.is_downloaded.return_value = False
        audio_svc.stop.return_value = "/tmp/recording.wav"
        controller.set_models(["base"])
        _force_recording(controller)
        result = controller.stop_and_save()
        assert result.wav_path == "/tmp/recording.wav"

    def test_wav_always_kept_regardless_of_setting(
        self, controller, audio_svc, model_svc, config_svc
    ):
        model_svc.is_downloaded.return_value = False
        config_svc.keep_wav = False
        controller.set_models(["base"])
        _force_recording(controller)
        controller.stop_and_save()
        model_svc.cleanup_wav.assert_not_called()

    def test_transitions_to_done(self, controller, audio_svc, model_svc):
        model_svc.is_downloaded.return_value = False
        controller.set_models(["base"])
        _force_recording(controller)
        controller.stop_and_save()
        assert controller.state == ControllerState.DONE

    def test_calls_audio_stop(self, controller, audio_svc, model_svc):
        model_svc.is_downloaded.return_value = False
        controller.set_models(["base"])
        _force_recording(controller)
        controller.stop_and_save()
        audio_svc.stop.assert_called_once()

    def test_no_models_selected_is_also_no_model_mode(
        self, controller, audio_svc, model_svc
    ):
        controller.set_models([])
        _force_recording(controller)
        result = controller.stop_and_save()
        assert result.is_no_model_mode is True

    def test_raises_if_not_recording(self, controller):
        with pytest.raises(RuntimeError):
            controller.stop_and_save()


# ---------------------------------------------------------------------------
# stop_and_save() — with models (transcription)
# ---------------------------------------------------------------------------


class TestStopAndSaveWithModels:
    def test_transitions_to_transcribing(self, controller, audio_svc, model_svc):
        model_svc.is_downloaded.return_value = True
        controller.set_models(["base"])
        _force_recording(controller)
        with patch.object(controller, "_run_transcription"):
            controller.stop_and_save()
        assert controller.state == ControllerState.TRANSCRIBING

    def test_returns_result_with_no_model_mode_false(
        self, controller, audio_svc, model_svc
    ):
        model_svc.is_downloaded.return_value = True
        controller.set_models(["base"])
        _force_recording(controller)
        with patch.object(controller, "_run_transcription"):
            result = controller.stop_and_save()
        assert result.is_no_model_mode is False

    def test_returns_result_with_wav_path(self, controller, audio_svc, model_svc):
        model_svc.is_downloaded.return_value = True
        audio_svc.stop.return_value = "/tmp/session.wav"
        controller.set_models(["base"])
        _force_recording(controller)
        with patch.object(controller, "_run_transcription"):
            result = controller.stop_and_save()
        assert result.wav_path == "/tmp/session.wav"

    def test_progress_list_initialized_per_model(
        self, controller, audio_svc, model_svc
    ):
        model_svc.is_downloaded.side_effect = lambda m: m in ("base", "small")
        controller.set_models(["base", "small"])
        _force_recording(controller)
        with patch.object(controller, "_run_transcription"):
            controller.stop_and_save()
        assert len(controller._progress) == 2
        names = [p.model_name for p in controller._progress]
        assert "base" in names
        assert "small" in names

    def test_calls_audio_stop(self, controller, audio_svc, model_svc):
        model_svc.is_downloaded.return_value = True
        controller.set_models(["base"])
        _force_recording(controller)
        with patch.object(controller, "_run_transcription"):
            controller.stop_and_save()
        audio_svc.stop.assert_called_once()


# ---------------------------------------------------------------------------
# _run_transcription() — synchronous transcription logic
# ---------------------------------------------------------------------------


class TestRunTranscription:
    def test_calls_transcribe_for_each_model(
        self, controller, model_svc
    ):
        mock_result = MagicMock()
        model_svc.transcribe.return_value = mock_result
        model_svc.save_transcript.return_value = Path("/tmp/x_base.md")
        controller._state = ControllerState.TRANSCRIBING
        controller._progress = [
            ModelProgress(model_name="base", progress=0.0),
        ]

        controller._run_transcription(
            wav_path="/tmp/session.wav",
            models=["base"],
            notes=[],
            save_folder="~/transcripts",
        )

        model_svc.transcribe.assert_called_once()
        call_kwargs = model_svc.transcribe.call_args
        assert call_kwargs[1].get("model_size") == "base" or call_kwargs[0][1] == "base"

    def test_calls_save_transcript_per_model(
        self, controller, model_svc
    ):
        mock_result = MagicMock()
        model_svc.transcribe.return_value = mock_result
        model_svc.save_transcript.return_value = Path("/tmp/x_base.md")
        controller._state = ControllerState.TRANSCRIBING
        controller._progress = [
            ModelProgress(model_name="base", progress=0.0),
        ]

        controller._run_transcription(
            wav_path="/tmp/session.wav",
            models=["base"],
            notes=[],
            save_folder="~/transcripts",
        )

        model_svc.save_transcript.assert_called_once()

    def test_marks_progress_done_on_success(self, controller, model_svc):
        mock_result = MagicMock()
        model_svc.transcribe.return_value = mock_result
        model_svc.save_transcript.return_value = Path("/tmp/x_base.md")
        controller._state = ControllerState.TRANSCRIBING
        controller._progress = [
            ModelProgress(model_name="base", progress=0.0),
        ]

        controller._run_transcription(
            wav_path="/tmp/session.wav",
            models=["base"],
            notes=[],
            save_folder="~/transcripts",
        )

        assert controller._progress[0].is_done is True
        assert controller._progress[0].progress == 1.0
        assert controller._progress[0].md_path == "/tmp/x_base.md"

    def test_marks_error_on_transcription_failure(self, controller, model_svc):
        model_svc.transcribe.side_effect = RuntimeError("model load failed")
        controller._state = ControllerState.TRANSCRIBING
        controller._progress = [
            ModelProgress(model_name="base", progress=0.0),
        ]

        controller._run_transcription(
            wav_path="/tmp/session.wav",
            models=["base"],
            notes=[],
            save_folder="~/transcripts",
        )

        assert controller._progress[0].is_done is True
        assert controller._progress[0].error is not None
        assert "model load failed" in controller._progress[0].error

    def test_transitions_to_done_after_all_models(self, controller, model_svc):
        model_svc.transcribe.return_value = MagicMock()
        model_svc.save_transcript.return_value = Path("/tmp/x_base.md")
        controller._state = ControllerState.TRANSCRIBING
        controller._progress = [
            ModelProgress(model_name="base", progress=0.0),
        ]

        controller._run_transcription(
            wav_path="/tmp/session.wav",
            models=["base"],
            notes=[],
            save_folder="~/transcripts",
        )

        assert controller.state == ControllerState.DONE

    def test_two_models_produces_two_transcripts(self, controller, model_svc):
        model_svc.transcribe.return_value = MagicMock()
        model_svc.save_transcript.side_effect = [
            Path("/tmp/x_base.md"),
            Path("/tmp/x_small.md"),
        ]
        controller._state = ControllerState.TRANSCRIBING
        controller._progress = [
            ModelProgress(model_name="base", progress=0.0),
            ModelProgress(model_name="small", progress=0.0),
        ]

        controller._run_transcription(
            wav_path="/tmp/session.wav",
            models=["base", "small"],
            notes=[],
            save_folder="~/transcripts",
        )

        assert model_svc.transcribe.call_count == 2
        assert model_svc.save_transcript.call_count == 2

    def test_deletes_wav_when_keep_wav_false_and_all_succeeded(
        self, controller, model_svc, config_svc
    ):
        config_svc.keep_wav = False
        model_svc.transcribe.return_value = MagicMock()
        model_svc.save_transcript.return_value = Path("/tmp/x_base.md")
        controller._state = ControllerState.TRANSCRIBING
        controller._progress = [
            ModelProgress(model_name="base", progress=0.0),
        ]

        controller._run_transcription(
            wav_path="/tmp/session.wav",
            models=["base"],
            notes=[],
            save_folder="~/transcripts",
        )

        model_svc.cleanup_wav.assert_called_once()

    def test_keeps_wav_when_keep_wav_true(
        self, controller, model_svc, config_svc
    ):
        config_svc.keep_wav = True
        model_svc.transcribe.return_value = MagicMock()
        model_svc.save_transcript.return_value = Path("/tmp/x_base.md")
        controller._state = ControllerState.TRANSCRIBING
        controller._progress = [
            ModelProgress(model_name="base", progress=0.0),
        ]

        controller._run_transcription(
            wav_path="/tmp/session.wav",
            models=["base"],
            notes=[],
            save_folder="~/transcripts",
        )

        model_svc.cleanup_wav.assert_not_called()

    def test_keeps_wav_when_any_transcript_failed(
        self, controller, model_svc, config_svc
    ):
        config_svc.keep_wav = False
        model_svc.transcribe.side_effect = [
            MagicMock(),
            RuntimeError("failed"),
        ]
        model_svc.save_transcript.return_value = Path("/tmp/x_base.md")
        controller._state = ControllerState.TRANSCRIBING
        controller._progress = [
            ModelProgress(model_name="base", progress=0.0),
            ModelProgress(model_name="small", progress=0.0),
        ]

        controller._run_transcription(
            wav_path="/tmp/session.wav",
            models=["base", "small"],
            notes=[],
            save_folder="~/transcripts",
        )

        model_svc.cleanup_wav.assert_not_called()

    def test_run_transcription_does_not_set_done_if_cancelled(
        self, controller, model_svc
    ):
        model_svc.transcribe.return_value = MagicMock()
        model_svc.save_transcript.return_value = Path("/tmp/x_base.md")
        controller._state = ControllerState.TRANSCRIBING
        controller._progress = [ModelProgress(model_name="base", progress=0.0)]
        controller._cancelled = True

        controller._run_transcription(
            wav_path="/tmp/session.wav",
            models=["base"],
            notes=[],
            save_folder="~/transcripts",
        )

        assert controller.state != ControllerState.DONE


# ---------------------------------------------------------------------------
# get_transcription_progress()
# ---------------------------------------------------------------------------


class TestGetTranscriptionProgress:
    def test_returns_empty_list_when_idle(self, controller):
        result = controller.get_transcription_progress()
        assert result == []

    def test_returns_progress_entries_as_dicts(self, controller):
        controller._progress = [
            ModelProgress(
                model_name="base",
                progress=0.5,
                is_done=False,
            )
        ]
        result = controller.get_transcription_progress()
        assert len(result) == 1
        assert result[0]["model_name"] == "base"
        assert result[0]["progress"] == 0.5
        assert result[0]["is_done"] is False

    def test_includes_md_path_when_done(self, controller):
        controller._progress = [
            ModelProgress(
                model_name="base",
                progress=1.0,
                md_path="/tmp/x_base.md",
                is_done=True,
            )
        ]
        result = controller.get_transcription_progress()
        assert result[0]["md_path"] == "/tmp/x_base.md"

    def test_includes_error_when_failed(self, controller):
        controller._progress = [
            ModelProgress(
                model_name="base",
                progress=0.0,
                error="model not found",
                is_done=True,
            )
        ]
        result = controller.get_transcription_progress()
        assert result[0]["error"] == "model not found"
