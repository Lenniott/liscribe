"""Transcription engine — wraps faster-whisper for offline speech-to-text.

Responsibilities:
- Load whisper model (download on first use)
- Transcribe WAV → text segments with timestamps
- Provide progress callbacks
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from liscribe.config import load_config

logger = logging.getLogger(__name__)


class TranscriptionResult:
    """Holds the output of a transcription."""

    def __init__(
        self,
        text: str,
        segments: list[dict],
        language: str,
        duration: float,
    ):
        self.text = text
        self.segments = segments
        self.language = language
        self.duration = duration

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def get_model_path() -> Path:
    """Return the local cache directory for whisper models."""
    return Path.home() / ".cache" / "liscribe" / "models"


def load_model(model_size: str | None = None):
    """Load the whisper model. Downloads on first use."""
    from faster_whisper import WhisperModel

    if model_size is None:
        cfg = load_config()
        model_size = cfg.get("whisper_model", "base")

    logger.info("Loading whisper model: %s", model_size)

    model = WhisperModel(
        model_size,
        device="cpu",
        compute_type="int8",
        download_root=str(get_model_path()),
    )

    logger.info("Model loaded: %s", model_size)
    return model


def transcribe(
    wav_path: str | Path,
    model=None,
    model_size: str | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> TranscriptionResult:
    """Transcribe a WAV file to text.

    Args:
        wav_path: Path to the WAV file.
        model: Pre-loaded WhisperModel. If None, loads one.
        model_size: Model size to use if loading. Defaults to config.
        on_progress: Callback with progress 0.0–1.0. Called per segment.

    Returns:
        TranscriptionResult with full text, segments, language, and duration.
    """
    wav_path = Path(wav_path)
    if not wav_path.exists():
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    if model is None:
        model = load_model(model_size)

    logger.info("Transcribing: %s", wav_path)

    segments_iter, info = model.transcribe(
        str(wav_path),
        beam_size=5,
        language=None,  # auto-detect
        vad_filter=True,
    )

    total_duration = info.duration
    segments = []
    text_parts = []

    for seg in segments_iter:
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
        })
        text_parts.append(seg.text.strip())

        if on_progress and total_duration > 0:
            progress = min(seg.end / total_duration, 1.0)
            on_progress(progress)

    full_text = " ".join(text_parts)

    if on_progress:
        on_progress(1.0)

    logger.info(
        "Transcription complete: %d segments, %d words, language=%s",
        len(segments), len(full_text.split()), info.language,
    )

    return TranscriptionResult(
        text=full_text,
        segments=segments,
        language=info.language or "unknown",
        duration=total_duration,
    )
