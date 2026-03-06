"""Whisper model management and transcription service wrapping transcriber.py."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

from liscribe import transcriber as _transcriber
from liscribe import output as _output
from liscribe.notes import Note
from liscribe.transcriber import TranscriptionResult, WHISPER_MODEL_ORDER
from liscribe.services.config_service import ConfigService


class ModelService:
    """Download, load, and run faster-whisper models.

    Created once in app.py and shared across all controllers.
    Panels never instantiate this directly.
    """

    def __init__(self, config: ConfigService) -> None:
        self._config = config
        self._loaded_models: dict[str, object] = {}
        self._download_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_models(self) -> list[dict]:
        """Return all known models with download status.

        Each dict has keys: name, is_downloaded, size_label.
        """
        size_labels = {
            "tiny": "~75 MB",
            "base": "~145 MB",
            "small": "~465 MB",
            "medium": "~1.5 GB",
            "large": "~3 GB",
        }
        return [
            {
                "name": name,
                "is_downloaded": _transcriber.is_model_available(name),
                "size_label": size_labels.get(name, ""),
            }
            for name in WHISPER_MODEL_ORDER
        ]

    def is_downloaded(self, model: str) -> bool:
        return _transcriber.is_model_available(model)

    def get_model_cache_dir(self, model: str) -> Path:
        return _transcriber.get_model_cache_dir(model)

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(
        self,
        model: str,
        on_progress: Callable[[float], None] | None = None,
    ) -> None:
        """Download a model, blocking the calling thread until complete.

        Calls on_progress(1.0) when the download finishes. Incremental
        progress is not available from the engine layer; callers should
        run this in a worker thread and show an indeterminate indicator
        until the call returns.
        """
        with self._download_lock:
            _transcriber.load_model(model)
            if on_progress:
                on_progress(1.0)

    def remove(self, model: str) -> tuple[bool, str]:
        """Remove a downloaded model. Returns (success, message)."""
        self._loaded_models.pop(model, None)
        return _transcriber.remove_model(model)

    # ------------------------------------------------------------------
    # Transcription
    # ------------------------------------------------------------------

    def transcribe(
        self,
        wav_path: str | Path,
        model_size: str | None = None,
        on_progress: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file. Loads model if not already loaded.

        Blocks the calling thread. Run in a worker thread from controllers.
        """
        if model_size is None:
            model_size = self._config.whisper_model

        if model_size not in self._loaded_models:
            self._loaded_models[model_size] = _transcriber.load_model(model_size)

        model = self._loaded_models[model_size]

        def _progress(progress: float, info: dict | None = None) -> None:
            if on_progress:
                on_progress(progress)

        return _transcriber.transcribe(
            audio_path=wav_path,
            model=model,
            model_size=model_size,
            on_progress=_progress if on_progress else None,
        )

    # ------------------------------------------------------------------
    # Output (Phase 4) — wraps output.py so controllers never import it
    # ------------------------------------------------------------------

    def save_transcript(
        self,
        result: TranscriptionResult,
        wav_path: str | Path,
        notes: list[Note] | None = None,
        model_name: str | None = None,
        save_folder: str | Path | None = None,
    ) -> Path:
        """Write a transcript to a Markdown file and return the path.

        Wraps output.save_transcript() so the controller layer never
        imports engine files directly.
        """
        return _output.save_transcript(
            result=result,
            audio_path=wav_path,
            notes=notes,
            model_name=model_name,
            include_model_in_filename=True,
            output_dir=save_folder,
        )

    def cleanup_wav(
        self,
        wav_path: str | Path,
        md_paths: list[str | Path],
    ) -> bool:
        """Delete the WAV only if every transcript file exists and is non-empty.

        Wraps output.cleanup_audio() — safe to call; never deletes the WAV
        unless all transcripts are confirmed written.
        """
        return _output.cleanup_audio(wav_path, md_paths)
