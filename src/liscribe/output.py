"""Output pipeline — Markdown generation, clipboard, audio cleanup.

Key rule: audio files are ONLY deleted after the transcript MD is
successfully written to disk.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import yaml

from liscribe.config import load_config
from liscribe.notes import Note
from liscribe.transcriber import TranscriptionResult

logger = logging.getLogger(__name__)


def _find_segment_for_note(
    segments: list[dict],
    timestamp: float,
) -> int:
    """Return the index of the segment active at *timestamp*.

    Falls back to the nearest segment when the timestamp lands in a gap.
    """
    for i, seg in enumerate(segments):
        if seg["start"] <= timestamp <= seg["end"]:
            return i

    best_idx = 0
    best_dist = float("inf")
    for i, seg in enumerate(segments):
        dist = min(abs(seg["start"] - timestamp), abs(seg["end"] - timestamp))
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return best_idx


def _build_annotated_transcript(
    segments: list[dict],
    notes: list[Note],
) -> str:
    """Build transcript text with inline ``[segment text][i]`` refs.

    Each note is mapped to a segment by its timestamp; segments without
    notes are emitted as plain text.
    """
    seg_notes: dict[int, list[int]] = defaultdict(list)
    for note in notes:
        idx = _find_segment_for_note(segments, note.timestamp)
        seg_notes[idx].append(note.index)

    parts: list[str] = []
    for i, seg in enumerate(segments):
        text = seg["text"]
        if i in seg_notes:
            refs = "".join(f"[{n}]" for n in seg_notes[i])
            parts.append(f"[{text}]{refs}")
        else:
            parts.append(text)

    return " ".join(parts)


def build_markdown(
    result: TranscriptionResult,
    wav_path: str | Path,
    notes: list[Note] | None = None,
    mic_name: str = "unknown",
    speaker_mode: bool = False,
) -> str:
    """Build a Markdown string with YAML front matter for a transcription."""
    wav_path = Path(wav_path)
    now = datetime.now()

    front_matter = {
        "title": f"Transcript {now.strftime('%Y-%m-%d %H:%M')}",
        "date": now.isoformat(),
        "duration_seconds": round(result.duration, 1),
        "word_count": result.word_count,
        "language": result.language,
        "mic": mic_name,
        "speaker_capture": speaker_mode,
        "source_audio": wav_path.name,
        "model": load_config().get("whisper_model", "base"),
    }

    lines = ["---"]
    lines.append(yaml.dump(front_matter, default_flow_style=False, sort_keys=False).strip())
    lines.append("---")
    lines.append("")
    lines.append("## Transcript")
    lines.append("")

    if notes and result.segments:
        lines.append(_build_annotated_transcript(result.segments, notes))
    else:
        lines.append(result.text)
    lines.append("")

    if notes:
        lines.append("## Notes")
        lines.append("")
        for note in notes:
            lines.append(f"[^{note.index}]: {note.text}")
        lines.append("")

    return "\n".join(lines)


def save_transcript(
    result: TranscriptionResult,
    wav_path: str | Path,
    notes: list[Note] | None = None,
    mic_name: str = "unknown",
    speaker_mode: bool = False,
) -> Path:
    """Write transcript to a .md file in the same folder as the WAV.

    Returns the path to the saved MD file.
    """
    wav_path = Path(wav_path)
    md_path = wav_path.with_suffix(".md")

    content = build_markdown(
        result=result,
        wav_path=wav_path,
        notes=notes,
        mic_name=mic_name,
        speaker_mode=speaker_mode,
    )

    md_path.write_text(content, encoding="utf-8")
    logger.info("Transcript saved: %s", md_path)
    return md_path


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard. Returns True on success."""
    try:
        import pyperclip
        pyperclip.copy(text)
        logger.info("Transcript copied to clipboard.")
        return True
    except Exception as exc:
        logger.warning("Could not copy to clipboard: %s", exc)
        return False


def cleanup_audio(wav_path: str | Path, md_path: str | Path) -> bool:
    """Delete the WAV file ONLY if the MD transcript exists and is non-empty.

    This is the critical safety check: never delete audio without a saved transcript.
    """
    wav_path = Path(wav_path)
    md_path = Path(md_path)

    if not md_path.exists():
        logger.error("Refusing to delete audio: transcript not found at %s", md_path)
        return False

    if md_path.stat().st_size == 0:
        logger.error("Refusing to delete audio: transcript is empty at %s", md_path)
        return False

    try:
        wav_path.unlink()
        logger.info("Audio file removed: %s", wav_path)
        return True
    except OSError as exc:
        logger.error("Could not delete audio file %s: %s", wav_path, exc)
        return False
