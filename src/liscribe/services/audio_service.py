"""Single-instance audio recording service wrapping recorder.py."""

from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

from liscribe.recorder import (
    RecordingSession,
    list_input_devices,
    resolve_saved_mic,
)
from liscribe.services.config_service import ConfigService


class AudioService:
    """Manages one active recording session at a time.

    Created once in app.py and shared across all controllers.
    Panels never instantiate this directly.
    """

    def __init__(self, config: ConfigService) -> None:
        self._config = config
        self._session: RecordingSession | None = None
        self._thread: threading.Thread | None = None
        self._wav_path: str | None = None

    # ------------------------------------------------------------------
    # Device enumeration
    # ------------------------------------------------------------------

    def list_mics(self) -> list[dict[str, Any]]:
        """Return available input devices."""
        return list_input_devices()

    def preferred_mic_index(self) -> int | None:
        """Return the saved default mic index, or None for system default."""
        saved = self._config.default_mic
        if saved:
            return resolve_saved_mic(saved)
        return None

    # ------------------------------------------------------------------
    # Recording lifecycle
    # ------------------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        return self._session is not None and self._thread is not None and self._thread.is_alive()

    def start(self, mic: str | None = None, speaker: bool = False) -> None:
        """Start a new recording session in a background thread.

        Raises RuntimeError if a recording is already in progress.
        """
        if self.is_recording:
            raise RuntimeError("A recording session is already active.")

        folder = self._config.save_folder
        self._session = RecordingSession(folder=folder, speaker=speaker, mic=mic)
        self._wav_path = None
        self._thread = threading.Thread(target=self._run, daemon=True, name="audio-recorder")
        self._thread.start()

    def _run(self) -> None:
        if self._session is None:
            return
        # Suppress recorder CLI print() when running from GUI (engine is frozen).
        with open(os.devnull, "w") as devnull:
            old_stdout, old_stderr = sys.stdout, sys.stderr
            try:
                sys.stdout = sys.stderr = devnull
                self._wav_path = self._session.start()
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr

    def stop(self) -> str | None:
        """Signal the active session to stop and wait for the WAV to be saved.

        Returns the path to the saved WAV file, or None if nothing was recorded.
        """
        if self._session is None:
            return None
        self._session._stop_requested.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        path = self._wav_path
        self._session = None
        self._thread = None
        self._wav_path = None
        return path

    def cancel(self) -> None:
        """Stop the active recording and delete any saved files from disk.

        In single-stream mode, deletes the WAV file.
        In dual-source mode, deletes the entire session directory
        (mic.wav + speaker.wav + session.json).
        """
        path_str = self.stop()
        if not path_str:
            return
        p = Path(path_str)
        session_dir = p.parent
        if (session_dir / "session.json").exists():
            shutil.rmtree(session_dir, ignore_errors=True)
            logger.info("Discarded dual-source session: %s", session_dir)
        else:
            p.unlink(missing_ok=True)
            logger.info("Discarded recording: %s", p)

    # ------------------------------------------------------------------
    # Mid-session controls (Phase 4)
    # ------------------------------------------------------------------

    def switch_mic(self, mic_name: str | None) -> None:
        """Switch the active microphone mid-recording.

        Resolves the name to a device index and delegates to
        RecordingSession.switch_mic().  Safe to call when not recording.
        """
        if self._session is None:
            return
        from liscribe.recorder import resolve_device

        try:
            idx = resolve_device(mic_name)
        except ValueError as exc:
            logger.warning("Cannot switch mic: %s", exc)
            return
        self._session.switch_mic(idx)

    def enable_speaker_capture(self) -> str | None:
        """Enable speaker capture on the active session.

        Returns None on success, or an error message string on failure.
        Safe to call when not recording (returns an error message).
        """
        if self._session is None:
            return "No active recording session."
        return self._session.enable_speaker_capture()

    def disable_speaker_capture(self) -> None:
        """Disable speaker capture on the active session. Safe when idle."""
        if self._session is None:
            return
        self._session.disable_speaker_capture()

    def get_session_start_time(self) -> float | None:
        """Return the wall-clock start time of the active session, or None."""
        if self._session is None:
            return None
        return self._session._start_time or None

    # ------------------------------------------------------------------
    # Real-time levels (for waveform display — Phase 4)
    # ------------------------------------------------------------------

    def get_levels(self, bars: int = 30) -> list[float]:
        """Return instantaneous RMS levels (0.0–1.0) for waveform display.

        When speaker capture is on, returns mic levels then speaker levels
        (length 2*bars) so the UI can show two rows. When speaker is off or
        has no data yet, returns mic levels only (length bars).
        """
        if self._session is None:
            return []
        with self._session._lock:
            if not self._session._mic_chunks:
                return [0.0] * bars
            mic_chunk = self._session._mic_chunks[-1].flatten()
            speaker_chunk = None
            if self._session.speaker and self._session._speaker_chunks:
                speaker_chunk = self._session._speaker_chunks[-1].flatten()

        def _levels_from_chunk(chunk: np.ndarray) -> list[float]:
            if len(chunk) == 0:
                return [0.0] * bars
            bar_size = max(1, len(chunk) // bars)
            out: list[float] = []
            for i in range(bars):
                segment = chunk[i * bar_size : (i + 1) * bar_size]
                rms = float(np.sqrt(np.mean(np.square(segment)))) if len(segment) > 0 else 0.0
                out.append(min(1.0, rms * 10.0))
            return out

        mic_levels = _levels_from_chunk(mic_chunk)
        if self._session.speaker:
            if speaker_chunk is not None:
                speaker_levels = _levels_from_chunk(speaker_chunk)
            else:
                speaker_levels = [0.0] * bars
            return mic_levels + speaker_levels
        return mic_levels
