"""Whisper model management and transcription service wrapping transcriber.py."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Callable

from liscribe import transcriber as _transcriber
from liscribe import output as _output
from liscribe import replacements as _replacements
from liscribe.notes import Note
from liscribe.transcriber import (
    TranscriptionResult,
    WHISPER_MODEL_ORDER,
    build_merged_transcription_result,
)
from liscribe.services.config_service import ConfigService

logger = logging.getLogger(__name__)


def _load_dual_source_session(audio_path: Path) -> dict | None:
    """Return dual-source session details when *audio_path* points to session mic.wav."""
    if audio_path.name.lower() != "mic.wav":
        return None
    session_dir = audio_path.parent
    speaker_path = session_dir / "speaker.wav"
    session_json_path = session_dir / "session.json"
    if not speaker_path.exists() or not session_json_path.exists():
        return None

    offset = 0.0
    try:
        session_meta = json.loads(session_json_path.read_text(encoding="utf-8"))
        offset = float(session_meta.get("offset_correction_seconds", 0.0))
    except Exception:
        offset = 0.0

    return {
        "session_dir": session_dir,
        "session_json_path": session_json_path,
        "mic_audio_path": audio_path,
        "speaker_audio_path": speaker_path,
        "speaker_offset_seconds": offset,
    }


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

    _SIZE_LABELS = {
        "tiny": "~75 MB",
        "base": "~145 MB",
        "small": "~465 MB",
        "medium": "~1.5 GB",
        "large": "~3 GB",
    }

    def list_models(self) -> list[dict]:
        """Return all known models with download status.

        Each dict has keys: name, is_downloaded, size_label.
        """
        return [
            {
                "name": name,
                "is_downloaded": _transcriber.is_model_available(name),
                "size_label": self._SIZE_LABELS.get(name, ""),
            }
            for name in WHISPER_MODEL_ORDER
        ]

    def list_models_fast(self) -> list[dict]:
        """Return model list without checking disk. Same shape as list_models().

        Use when only names/order are needed (e.g. Transcribe panel) to avoid
        blocking the main thread on filesystem during panel load.
        """
        return [
            {
                "name": name,
                "is_downloaded": True,
                "size_label": self._SIZE_LABELS.get(name, ""),
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

        When wav_path points to a dual-source session (mic.wav with speaker.wav
        and session.json in the same dir), transcribes both streams, merges
        with source labels and mic-bleed dedup, and returns the merged result.

        Blocks the calling thread. Run in a worker thread from controllers.
        """
        wav_path = Path(wav_path)
        if model_size is None:
            model_size = self._config.whisper_model

        if model_size not in self._loaded_models:
            self._loaded_models[model_size] = _transcriber.load_model(model_size)

        model = self._loaded_models[model_size]

        def _progress(progress: float, info: dict | None = None) -> None:
            if on_progress:
                on_progress(progress)

        dual = _load_dual_source_session(wav_path)
        if dual is not None:
            def mic_progress(p: float, info: dict | None = None) -> None:
                _progress(p * 0.5)

            def speaker_progress(p: float, info: dict | None = None) -> None:
                _progress(0.5 + p * 0.5)

            mic_result = _transcriber.transcribe(
                audio_path=dual["mic_audio_path"],
                model=model,
                model_size=model_size,
                on_progress=mic_progress if on_progress else None,
            )
            speaker_result = _transcriber.transcribe(
                audio_path=dual["speaker_audio_path"],
                model=model,
                model_size=model_size,
                on_progress=speaker_progress if on_progress else None,
            )
            return build_merged_transcription_result(
                mic_result=mic_result,
                speaker_result=speaker_result,
                speaker_offset_seconds=float(dual["speaker_offset_seconds"]),
                group_consecutive=self._config.group_consecutive_speaker_lines,
                suppress_mic_bleed_duplicates=self._config.suppress_mic_bleed_duplicates,
                bleed_similarity_threshold=self._config.mic_bleed_similarity_threshold,
                model_name=model_size,
            )

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
        filename_stem: str | None = None,
    ) -> Path:
        """Write a transcript to a Markdown file and return the path.

        When wav_path points to a dual-source session (mic.wav), pass
        filename_stem (e.g. session dir name) so the transcript is named
        after the session, not \"mic\". If filename_stem is None and
        wav_path is a session mic.wav, it is inferred from the session dir.

        Applies word replacement rules (scope \"transcripts\") before writing.
        Builds markdown via output.build_markdown; does not call output.save_transcript
        so we can apply replacements without modifying the frozen engine file.
        """
        wav_path = Path(wav_path)
        if filename_stem is None:
            dual = _load_dual_source_session(wav_path)
            if dual is not None:
                filename_stem = dual["session_dir"].name
        stem = filename_stem or wav_path.stem
        suffix = f"_{model_name}" if model_name else ""
        filename = f"{stem}{suffix}.md"
        parent = (
            Path(save_folder).expanduser().resolve()
            if save_folder
            else wav_path.parent
        )
        md_path = parent / filename
        parent.mkdir(parents=True, exist_ok=True)

        content = _output.build_markdown(
            result=result,
            audio_path=wav_path,
            notes=notes,
            mic_name="unknown",
            speaker_mode=False,
            model_name=model_name,
        )
        content = _replacements.apply(
            content,
            self._config.replacement_rules,
            "transcripts",
        )
        md_path.write_text(content, encoding="utf-8")
        md_path.chmod(0o600)
        logger.info("Transcript saved: %s", md_path)
        return md_path

    def cleanup_wav(
        self,
        wav_path: str | Path,
        md_paths: list[str | Path],
    ) -> bool:
        """Delete the WAV only if every transcript file exists and is non-empty.

        When wav_path points to a dual-source session (mic.wav), also deletes
        speaker.wav and session.json in the same directory.

        Wraps output.cleanup_audio() — safe to call; never deletes the WAV
        unless all transcripts are confirmed written.
        """
        wav_path = Path(wav_path)
        dual = _load_dual_source_session(wav_path)
        ok = _output.cleanup_audio(wav_path, md_paths)
        if dual and ok:
            ok = _output.cleanup_audio(
                dual["speaker_audio_path"],
                md_paths,
            ) and ok
            try:
                dual["session_json_path"].unlink(missing_ok=True)
            except OSError:
                ok = False
        return ok
