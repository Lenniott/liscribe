"""Transcription engine — wraps faster-whisper for offline speech-to-text.

Responsibilities:
- Load whisper model (download on first use)
- Transcribe audio → text segments with timestamps
- Provide progress callbacks
- Check model availability without downloading
"""

from __future__ import annotations

import logging
import math
import re
import shutil
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Callable

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

# Optional progress info for ETA: segment_index, total_estimated, elapsed_sec, eta_remaining_sec
ProgressInfo = dict

from liscribe.config import load_config

logger = logging.getLogger(__name__)

MODEL_REPO_IDS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large": "Systran/faster-whisper-large-v3",
}


class TranscriptionResult:
    """Holds the output of a transcription."""

    def __init__(
        self,
        text: str,
        segments: list[dict],
        language: str,
        duration: float,
        model_name: str = "base",
        metadata: dict | None = None,
    ):
        self.text = text
        self.segments = segments
        self.language = language
        self.duration = duration
        self.model_name = model_name
        self.metadata = metadata or {}

    @property
    def word_count(self) -> int:
        return len(self.text.split())


def get_model_path() -> Path:
    """Return the local cache directory for whisper models."""
    return Path.home() / ".cache" / "liscribe" / "models"


def get_model_cache_dir(model_size: str) -> Path:
    """Return cache directory for a specific model repo."""
    repo_id = MODEL_REPO_IDS.get(model_size, f"Systran/faster-whisper-{model_size}")
    return get_model_path() / f"models--{repo_id.replace('/', '--')}"


def is_model_available(model_size: str) -> bool:
    """Check whether a model is already downloaded (no network access)."""
    model_dir = get_model_cache_dir(model_size)
    if model_dir.is_dir():
        snapshots = model_dir / "snapshots"
        if snapshots.is_dir():
            return any(snapshots.iterdir())
    return False


def remove_model(model_size: str) -> tuple[bool, str]:
    """Remove a downloaded model from local cache."""
    model_dir = get_model_cache_dir(model_size)
    if not model_dir.exists():
        return False, f"Model not installed: {model_size}"
    try:
        shutil.rmtree(model_dir)
        return True, f"Removed model: {model_size}"
    except Exception as exc:
        return False, f"Could not remove {model_size}: {exc}"


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


# Average segment length in seconds used to estimate total segment count (for ETA).
AVG_SEGMENT_SEC = 6.0


def _to_float32_audio(audio_data: np.ndarray) -> np.ndarray:
    """Convert input waveform to float32 in [-1, 1]."""
    if np.issubdtype(audio_data.dtype, np.integer):
        info = np.iinfo(audio_data.dtype)
        scale = max(abs(info.min), info.max)
        return audio_data.astype(np.float32) / float(scale)
    return audio_data.astype(np.float32)


def _preprocess_wav_for_asr(audio_path: Path, target_sample_rate: int = 16000) -> tuple[Path, bool]:
    """Return (path, is_temporary) after mono/resample/normalization preprocessing."""
    if audio_path.suffix.lower() != ".wav":
        return audio_path, False

    try:
        sample_rate, audio_data = wavfile.read(str(audio_path))
    except Exception as exc:
        logger.warning("Skipping preprocessing for %s: %s", audio_path, exc)
        return audio_path, False

    if audio_data.size == 0:
        return audio_path, False

    audio = _to_float32_audio(audio_data)

    # Whisper is optimized for mono speech; averaging channels improves stability.
    if audio.ndim == 2:
        audio = audio.mean(axis=1)

    if sample_rate != target_sample_rate:
        gcd = math.gcd(int(sample_rate), int(target_sample_rate))
        up = target_sample_rate // gcd
        down = sample_rate // gcd
        audio = resample_poly(audio, up, down).astype(np.float32)

    # Mild RMS normalization: increase quiet audio without hard limiting.
    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    target_rms = 0.08
    if rms > 1e-6:
        gain = min(target_rms / rms, 4.0)
        audio = np.clip(audio * gain, -1.0, 1.0)

    tmp = tempfile.NamedTemporaryFile(prefix="liscribe_pre_", suffix=".wav", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    wavfile.write(str(tmp_path), target_sample_rate, np.clip(audio * 32767, -32768, 32767).astype(np.int16))
    return tmp_path, True


def _source_label(source: str) -> str:
    return "YOU" if source == "mic" else "THEM"


def _normalize_words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def _text_similarity(a: str, b: str) -> float:
    """Combined text similarity score in [0,1]."""
    a_clean = a.strip().lower()
    b_clean = b.strip().lower()
    if not a_clean or not b_clean:
        return 0.0

    seq_ratio = SequenceMatcher(None, a_clean, b_clean).ratio()

    wa = _normalize_words(a_clean)
    wb = _normalize_words(b_clean)
    if not wa or not wb:
        return seq_ratio
    token_jaccard = len(wa & wb) / max(1, len(wa | wb))
    token_containment = len(wa & wb) / max(1, min(len(wa), len(wb)))
    return max(seq_ratio, token_jaccard, token_containment)


def _tag_source_segments(segments: list[dict], source: str, offset_seconds: float = 0.0) -> list[dict]:
    tagged: list[dict] = []
    speaker = _source_label(source)
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        start = float(seg.get("start", 0.0)) + offset_seconds
        end = float(seg.get("end", start)) + offset_seconds
        start = max(0.0, start)
        end = max(start, end)
        tagged.append({
            "start": start,
            "end": end,
            "text": text,
            "source": source,
            "speaker": speaker,
        })
    return tagged


def _suppress_mic_bleed_duplicates(
    mic_segments: list[dict],
    speaker_segments: list[dict],
    similarity_threshold: float = 0.62,
) -> list[dict]:
    """Drop mic segments when they are similar to any speaker segment."""
    kept: list[dict] = []
    for mic_seg in mic_segments:
        is_duplicate = False
        for spk_seg in speaker_segments:
            similarity = _text_similarity(mic_seg["text"], spk_seg["text"])
            if similarity >= similarity_threshold:
                is_duplicate = True
                break
        if not is_duplicate:
            kept.append(mic_seg)
    return kept


def merge_source_segments(
    mic_segments: list[dict],
    speaker_segments: list[dict],
    speaker_offset_seconds: float = 0.0,
    group_consecutive: bool = False,
    suppress_mic_bleed_duplicates: bool = False,
    bleed_similarity_threshold: float = 0.62,
) -> list[dict]:
    """Merge mic and speaker segment lists into chronological source-labeled segments."""
    tagged_mic = _tag_source_segments(mic_segments, "mic")
    tagged_speaker = _tag_source_segments(
        speaker_segments,
        "speaker",
        offset_seconds=speaker_offset_seconds,
    )
    if suppress_mic_bleed_duplicates and tagged_mic and tagged_speaker:
        tagged_mic = _suppress_mic_bleed_duplicates(
            tagged_mic,
            tagged_speaker,
            similarity_threshold=bleed_similarity_threshold,
        )

    merged = tagged_mic + tagged_speaker
    merged.sort(key=lambda seg: (seg["start"], 0 if seg["source"] == "mic" else 1, seg["end"]))

    if not group_consecutive:
        return merged

    grouped: list[dict] = []
    for seg in merged:
        if not grouped:
            grouped.append(seg.copy())
            continue
        prev = grouped[-1]
        if seg["speaker"] == prev["speaker"]:
            prev["text"] = f"{prev['text']} {seg['text']}".strip()
            prev["end"] = max(prev["end"], seg["end"])
            continue
        grouped.append(seg.copy())
    return grouped


def build_merged_transcription_result(
    mic_result: TranscriptionResult,
    speaker_result: TranscriptionResult,
    speaker_offset_seconds: float = 0.0,
    group_consecutive: bool = False,
    suppress_mic_bleed_duplicates: bool = False,
    bleed_similarity_threshold: float = 0.62,
    model_name: str | None = None,
) -> TranscriptionResult:
    """Combine two independent source transcriptions into one chronological result."""
    merged_segments = merge_source_segments(
        mic_segments=mic_result.segments,
        speaker_segments=speaker_result.segments,
        speaker_offset_seconds=speaker_offset_seconds,
        group_consecutive=group_consecutive,
        suppress_mic_bleed_duplicates=suppress_mic_bleed_duplicates,
        bleed_similarity_threshold=bleed_similarity_threshold,
    )
    merged_text = "\n".join(f"{seg['speaker']}: {seg['text']}" for seg in merged_segments)
    duration = max(mic_result.duration, speaker_result.duration + max(0.0, speaker_offset_seconds))
    language = mic_result.language if mic_result.language != "unknown" else speaker_result.language
    return TranscriptionResult(
        text=merged_text,
        segments=merged_segments,
        language=language or "unknown",
        duration=duration,
        model_name=model_name or mic_result.model_name,
        metadata={
            "diarization": "source-based",
            "sources": {"mic": "YOU", "speaker": "THEM"},
            "speaker_offset_seconds": speaker_offset_seconds,
        },
    )


def transcribe(
    audio_path: str | Path,
    model=None,
    model_size: str | None = None,
    on_progress: Callable[..., None] | None = None,
) -> TranscriptionResult:
    """Transcribe an audio file to text.

    Args:
        audio_path: Path to the audio file (WAV, MP3, M4A, OGG, etc.).
        model: Pre-loaded WhisperModel. If None, loads one.
        model_size: Model size to use if loading. Defaults to config.
        on_progress: Callback(progress_0_1, info=None). progress_0_1 is 0.0–1.0.
            Optional info dict: segment_index, total_estimated, elapsed_sec, eta_remaining_sec.

    Returns:
        TranscriptionResult with full text, segments, language, and duration.
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if model is None:
        model = load_model(model_size)

    if model_size is None:
        cfg = load_config()
        model_size = cfg.get("whisper_model", "base")

    cfg = load_config()
    lang = cfg.get("language", "en")
    if lang == "auto":
        lang = None

    prepared_path, is_temp_file = _preprocess_wav_for_asr(audio_path)
    logger.info("Transcribing: %s (language=%s)", audio_path, lang or "auto")

    try:
        segments_iter, info = model.transcribe(
            str(prepared_path),
            beam_size=5,
            language=lang,
            vad_filter=True,
        )

        total_duration = info.duration
        segments = []
        text_parts = []

        # Estimate total segments for ETA (faster_whisper does not expose N).
        N = max(1, int(total_duration / AVG_SEGMENT_SEC))
        start_time = time.perf_counter()

        def _report_progress(segment_index: int, total_estimated: int, elapsed_sec: float) -> None:
            if not on_progress:
                return
            progress_float = min(segment_index / total_estimated, 1.0) if total_estimated else 0.0
            eta_remaining = (elapsed_sec * (total_estimated - segment_index) / segment_index) if segment_index > 0 else None
            info: ProgressInfo = {
                "segment_index": segment_index,
                "total_estimated": total_estimated,
                "elapsed_sec": elapsed_sec,
                "eta_remaining_sec": eta_remaining,
            }
            try:
                on_progress(progress_float, info)
            except TypeError:
                on_progress(progress_float)

        if on_progress:
            _report_progress(0, N, 0.0)

        for seg in segments_iter:
            segments.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            })
            text_parts.append(seg.text.strip())

            if on_progress:
                i = len(segments)
                elapsed = time.perf_counter() - start_time
                _report_progress(i, N, elapsed)

        full_text = " ".join(text_parts)

        if on_progress:
            _report_progress(N, N, time.perf_counter() - start_time)

        logger.info(
            "Transcription complete: %d segments, %d words, language=%s",
            len(segments), len(full_text.split()), info.language,
        )

        return TranscriptionResult(
            text=full_text,
            segments=segments,
            language=info.language or "unknown",
            duration=total_duration,
            model_name=model_size,
        )
    finally:
        if is_temp_file:
            try:
                prepared_path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Could not remove temp preprocessed file: %s", prepared_path)
