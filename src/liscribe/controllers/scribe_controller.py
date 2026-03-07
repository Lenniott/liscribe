"""Scribe workflow controller.

Orchestrates AudioService + ModelService for one recording session.
Single concern: managing the Scribe state machine and delegating to services.

State machine:
    IDLE → (start) → RECORDING → (stop_and_save) → TRANSCRIBING → DONE
    RECORDING → (cancel) → IDLE
    Any state → (cancel) → IDLE

Design note — notes.py import:
    NoteCollection and Note are pure-data value objects with no hardware or
    IO dependencies.  Importing them here does not violate the intent of the
    "engine files outside services" rule, which is specifically about
    hardware access (recorder.py, transcriber.py, output.py).  The import
    is documented here and nowhere else in the controller/bridge layers.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from liscribe.notes import NoteCollection

if TYPE_CHECKING:
    from liscribe.notes import Note
    from liscribe.services.audio_service import AudioService
    from liscribe.services.config_service import ConfigService
    from liscribe.services.model_service import ModelService

logger = logging.getLogger(__name__)


class ControllerState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    DONE = "done"


@dataclass
class ModelProgress:
    """Tracks transcription progress for one model."""

    model_name: str
    progress: float = 0.0
    md_path: str | None = None
    error: str | None = None
    is_done: bool = False


@dataclass
class ScribeResult:
    """Outcome returned by stop_and_save()."""

    wav_path: str | None
    transcripts: list[ModelProgress]
    is_no_model_mode: bool
    save_folder: str


class ScribeController:
    """Orchestrates one Scribe recording session.

    Receives all services as constructor arguments — never instantiates them.
    UI panels never interact with this class directly; they go through
    ScribeBridge.
    """

    def __init__(
        self,
        audio: AudioService,
        model: ModelService,
        config: ConfigService,
    ) -> None:
        self._audio = audio
        self._model = model
        self._config = config

        self._state = ControllerState.IDLE
        self._notes = NoteCollection()
        self._selected_models: list[str] = list(config.scribe_models)
        self._current_mic: str | None = None
        self._speaker_enabled: bool = False
        self._save_path: str | None = None
        self._is_using_fallback_mic: bool = False

        self._progress: list[ModelProgress] = []
        self._result: ScribeResult | None = None
        self._lock = threading.Lock()
        self._cancelled: bool = False

    # ------------------------------------------------------------------
    # Read-only state
    # ------------------------------------------------------------------

    @property
    def state(self) -> ControllerState:
        return self._state

    @property
    def is_recording(self) -> bool:
        return self._state == ControllerState.RECORDING

    @property
    def is_transcribing(self) -> bool:
        return self._state == ControllerState.TRANSCRIBING

    @property
    def is_using_fallback_mic(self) -> bool:
        return self._is_using_fallback_mic

    @property
    def selected_models(self) -> list[str]:
        return list(self._selected_models)

    @property
    def save_path(self) -> str:
        return self._save_path or self._config.save_folder

    @property
    def current_mic(self) -> str | None:
        return self._current_mic

    # ------------------------------------------------------------------
    # Recording lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start a new recording session.

        Raises RuntimeError if not in IDLE state.
        """
        if self._state != ControllerState.IDLE:
            raise RuntimeError(
                f"Cannot start: controller is in state '{self._state.value}'"
            )

        # Detect fallback mic before starting
        preferred = self._config.default_mic
        if preferred:
            resolved = self._audio.preferred_mic_index()
            self._is_using_fallback_mic = resolved is None
        else:
            self._is_using_fallback_mic = False

        self._cancelled = False
        self._notes = NoteCollection()
        self._audio.start(mic=self._current_mic, speaker=self._speaker_enabled)

        start_time = self._audio.get_session_start_time()
        if start_time:
            self._notes.start_from(start_time)
        else:
            self._notes.start()

        self._state = ControllerState.RECORDING

    def stop_and_save(self) -> ScribeResult:
        """Stop recording and initiate transcription.

        Transcription runs in a background thread. Returns the initial
        ScribeResult immediately; callers poll get_transcription_progress()
        for updates.

        Raises RuntimeError if not in RECORDING state.
        """
        if self._state != ControllerState.RECORDING:
            raise RuntimeError(
                f"Cannot stop: controller is in state '{self._state.value}'"
            )

        wav_path = self._audio.stop()
        notes = self._notes.notes
        save_folder = self.save_path
        downloaded_models = [
            m for m in self._selected_models if self._model.is_downloaded(m)
        ]

        if not downloaded_models:
            return self._stop_no_model(wav_path, save_folder)

        return self._stop_with_models(wav_path, downloaded_models, notes, save_folder)

    def _stop_no_model(self, wav_path: str | None, save_folder: str) -> ScribeResult:
        """Handle stop when no downloaded model is selected.

        WAV is always retained in this mode — it is the only output.
        """
        result = ScribeResult(
            wav_path=wav_path,
            transcripts=[],
            is_no_model_mode=True,
            save_folder=save_folder,
        )
        self._result = result
        self._state = ControllerState.DONE
        return result

    def _stop_with_models(
        self,
        wav_path: str | None,
        models: list[str],
        notes: list[Note],
        save_folder: str,
    ) -> ScribeResult:
        """Handle stop when at least one downloaded model is selected."""
        with self._lock:
            self._progress = [ModelProgress(model_name=m) for m in models]

        self._state = ControllerState.TRANSCRIBING

        result = ScribeResult(
            wav_path=wav_path,
            transcripts=self._progress,
            is_no_model_mode=False,
            save_folder=save_folder,
        )
        self._result = result

        thread = threading.Thread(
            target=self._run_transcription,
            kwargs={
                "wav_path": wav_path,
                "models": models,
                "notes": notes,
                "save_folder": save_folder,
            },
            daemon=True,
            name="scribe-transcriber",
        )
        thread.start()
        return result

    def cancel(self) -> None:
        """Discard the active recording without saving anything.

        Safe to call in any state, including IDLE.
        When in TRANSCRIBING, sets _cancelled so the background thread
        does not overwrite state to DONE.

        Resets all UI-relevant session state so the next session starts clean:
        notes, speaker_enabled, and state. When adding new session-scoped state,
        reset it here so cancel() keeps the contract.
        """
        if self._state == ControllerState.IDLE:
            return

        if self._state == ControllerState.RECORDING:
            self._audio.cancel()
        with self._lock:
            self._cancelled = True
        self._notes = NoteCollection()
        self._speaker_enabled = False
        self._state = ControllerState.IDLE

    # ------------------------------------------------------------------
    # Transcription (background thread)
    # ------------------------------------------------------------------

    def _run_transcription(
        self,
        wav_path: str | None,
        models: list[str],
        notes: list[Note],
        save_folder: str,
    ) -> None:
        """Run transcription for each model sequentially. Called in a daemon thread."""
        md_paths: list[Path] = []

        for i, model_name in enumerate(models):
            md_path = self._transcribe_one(i, model_name, wav_path, notes, save_folder)
            if md_path is not None:
                md_paths.append(md_path)

        all_succeeded = len(md_paths) == len(models)
        if not self._config.keep_wav and all_succeeded and wav_path:
            self._model.cleanup_wav(wav_path, [str(p) for p in md_paths])

        with self._lock:
            if not self._cancelled:
                self._state = ControllerState.DONE

    def _transcribe_one(
        self,
        index: int,
        model_name: str,
        wav_path: str | None,
        notes: list[Note],
        save_folder: str,
    ) -> Path | None:
        """Transcribe with one model and update progress. Returns md_path or None on error."""
        progress_entry = self._progress[index]

        def _on_progress(p: float, idx: int = index) -> None:
            with self._lock:
                self._progress[idx].progress = p

        try:
            result = self._model.transcribe(
                wav_path=wav_path,
                model_size=model_name,
                on_progress=_on_progress,
            )
            md_path = self._model.save_transcript(
                result=result,
                wav_path=wav_path,
                notes=notes or None,
                model_name=model_name,
                save_folder=save_folder,
            )
            with self._lock:
                progress_entry.progress = 1.0
                progress_entry.md_path = str(md_path)
                progress_entry.is_done = True
            return md_path

        except Exception as exc:
            logger.error("Transcription failed for model '%s': %s", model_name, exc)
            with self._lock:
                progress_entry.error = str(exc)
                progress_entry.is_done = True
            return None

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def add_note(self, text: str) -> Note:
        """Add a timestamped note to the current recording.

        Raises RuntimeError if not in RECORDING state.
        """
        if self._state != ControllerState.RECORDING:
            raise RuntimeError(
                "Cannot add note: not currently recording "
                f"(state is '{self._state.value}')"
            )
        return self._notes.add(text)

    # ------------------------------------------------------------------
    # Real-time data
    # ------------------------------------------------------------------

    def get_waveform(self, bars: int = 30) -> list[float]:
        """Return current audio level bars (0.0–1.0) for waveform display."""
        return self._audio.get_levels(bars=bars)

    def get_elapsed_seconds(self) -> float:
        """Return seconds elapsed since recording started, or 0.0."""
        if self._state != ControllerState.RECORDING:
            return 0.0
        start = self._audio.get_session_start_time()
        if start is None:
            return 0.0
        return time.time() - start

    def get_transcription_progress(self) -> list[dict]:
        """Return a JSON-serialisable snapshot of per-model progress."""
        with self._lock:
            return [
                {
                    "model_name": p.model_name,
                    "progress": p.progress,
                    "md_path": p.md_path,
                    "error": p.error,
                    "is_done": p.is_done,
                }
                for p in self._progress
            ]

    # ------------------------------------------------------------------
    # Session configuration (can be changed before or during recording)
    # ------------------------------------------------------------------

    def set_mic(self, mic_name: str | None) -> None:
        """Set the microphone for the next recording start."""
        self._current_mic = mic_name

    def switch_mic(self, mic_name: str | None) -> None:
        """Swap the active microphone mid-recording.

        Only acts when in RECORDING state; otherwise a no-op.
        """
        if self._state != ControllerState.RECORDING:
            return
        self._audio.switch_mic(mic_name)

    def set_speaker(self, enabled: bool) -> str | None:
        """Enable or disable speaker capture.

        When called during a recording, immediately applies the change.
        Returns None on success, or an error message string on failure.
        """
        self._speaker_enabled = enabled
        if self._state == ControllerState.RECORDING:
            if enabled:
                return self._audio.enable_speaker_capture()
            else:
                self._audio.disable_speaker_capture()
        return None

    def set_save_path(self, path: str) -> None:
        """Override the save folder for this session."""
        self._save_path = path

    def set_models(self, model_names: list[str]) -> None:
        """Set the models to use for transcription after stop."""
        self._selected_models = list(model_names)

    # ------------------------------------------------------------------
    # Open transcript in external app (same behaviour as Transcribe panel)
    # ------------------------------------------------------------------

    def open_transcript(self, file_path: str) -> None:
        """Open the transcript file with the app set in Settings."""
        self._config.open_transcript(file_path)
