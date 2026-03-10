"""Transcribe workflow controller.

Orchestrates ModelService for file-based transcription. Single concern:
managing Transcribe panel state and delegating to the model service.
No direct engine imports.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from liscribe.services.config_service import ConfigService
    from liscribe.services.model_service import ModelService

logger = logging.getLogger(__name__)

# Allowed audio file extensions for Transcribe (rubric: .wav .mp3 .m4a)
ALLOWED_AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a")


class TranscribeState(str, Enum):
    IDLE = "idle"
    TRANSCRIBING = "transcribing"
    DONE = "done"


@dataclass
class ModelProgress:
    """Progress for one model in a Transcribe run."""

    model_name: str
    progress: float = 0.0
    md_path: str | None = None
    error: str | None = None
    is_done: bool = False


@dataclass
class PrefillState:
    """One-time prefill for "Open in Transcribe" from Scribe."""

    audio_path: str = ""
    output_folder: str = ""


class TranscribeController:
    """Orchestrates one Transcribe session (file → models → output files).

    Receives config and model services as constructor arguments.
    """

    def __init__(
        self,
        config: ConfigService,
        model: ModelService,
    ) -> None:
        self._config = config
        self._model = model
        self._state = TranscribeState.IDLE
        self._audio_path: str | None = None
        self._output_folder_override: str | None = None
        self._selected_models: list[str] = list(config.scribe_models)
        self._prefill: PrefillState | None = None
        self._progress: list[ModelProgress] = []
        self._lock = threading.Lock()
        self._cancelled: bool = False

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def state(self) -> TranscribeState:
        return self._state

    @property
    def audio_path(self) -> str | None:
        return self._audio_path

    @property
    def output_folder(self) -> str:
        return self._output_folder_override or self._config.save_folder

    @property
    def selected_models(self) -> list[str]:
        return list(self._selected_models)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _allowed_extension(path: str) -> bool:
        p = Path(path)
        suf = p.suffix.lower() if p.suffix else ""
        return suf in (e.lower() for e in ALLOWED_AUDIO_EXTENSIONS)

    # ------------------------------------------------------------------
    # Session config
    # ------------------------------------------------------------------

    def set_audio_path(self, path: str | None) -> None:
        if path is None or path.strip() == "":
            self._audio_path = None
            return
        if not self._allowed_extension(path):
            raise ValueError(
                f"File type not allowed. Use one of: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}"
            )
        self._audio_path = path.strip()

    def set_output_folder(self, path: str) -> None:
        self._output_folder_override = path.strip() if path else None

    def set_models(self, model_names: list[str]) -> None:
        self._selected_models = list(model_names)

    def set_prefill(self, audio_path: str, output_folder: str) -> None:
        self._prefill = PrefillState(
            audio_path=audio_path or "",
            output_folder=output_folder or "",
        )

    def get_prefill(self) -> dict:
        """Return and consume one-time prefill (e.g. from Scribe 'Open in Transcribe')."""
        if self._prefill is None:
            return {"audio_path": "", "output_folder": self._config.save_folder}
        out = {
            "audio_path": self._prefill.audio_path,
            "output_folder": self._prefill.output_folder or self._config.save_folder,
        }
        self._prefill = None
        return out

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def start_transcribe(self) -> None:
        if self._state != TranscribeState.IDLE:
            raise RuntimeError(
                f"Cannot start transcribe: state is '{self._state.value}'"
            )
        if not self._audio_path:
            raise RuntimeError("No audio file selected.")
        downloaded = [m for m in self._selected_models if self._model.is_downloaded(m)]
        if not downloaded:
            raise RuntimeError(
                "No downloaded models selected. Download at least one model in Settings."
            )

        with self._lock:
            self._progress = [ModelProgress(model_name=m) for m in downloaded]
            self._cancelled = False
        self._state = TranscribeState.TRANSCRIBING

        thread = threading.Thread(
            target=self._run_transcription,
            kwargs={
                "audio_path": self._audio_path,
                "models": downloaded,
                "output_folder": self.output_folder,
            },
            daemon=True,
            name="transcribe-worker",
        )
        thread.start()

    def _run_transcription(
        self,
        audio_path: str,
        models: list[str],
        output_folder: str,
    ) -> None:
        for i, model_name in enumerate(models):
            with self._lock:
                if self._cancelled:
                    break
            entry = self._progress[i]

            def _on_progress(p: float, idx: int = i) -> None:
                with self._lock:
                    if idx < len(self._progress):
                        self._progress[idx].progress = p

            try:
                result = self._model.transcribe(
                    wav_path=audio_path,
                    model_size=model_name,
                    on_progress=_on_progress,
                )
                md_path = self._model.save_transcript(
                    result=result,
                    wav_path=audio_path,
                    notes=None,
                    model_name=model_name,
                    save_folder=output_folder,
                )
                with self._lock:
                    entry.progress = 1.0
                    entry.md_path = str(md_path)
                    entry.is_done = True
            except Exception as exc:
                logger.exception("Transcription failed for model %s", model_name)
                with self._lock:
                    entry.error = str(exc)
                    entry.is_done = True

        with self._lock:
            if not self._cancelled:
                self._state = TranscribeState.DONE

    def cancel(self) -> None:
        """Cancel in-progress transcription. Safe to call in any state.

        Sets a flag that stops the background thread after its current model.
        When cancelled, the state transitions to IDLE (not DONE).
        """
        if self._state == TranscribeState.IDLE:
            return
        with self._lock:
            self._cancelled = True
        self._state = TranscribeState.IDLE

    def get_progress(self) -> list[dict]:
        """Return JSON-serialisable progress for the UI."""
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
    # Open transcript in external app
    # ------------------------------------------------------------------

    def open_transcript(self, file_path: str) -> None:
        """Open the transcript file with the app set in Settings."""
        self._config.open_transcript(file_path)
