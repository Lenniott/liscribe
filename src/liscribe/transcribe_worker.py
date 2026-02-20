"""Run transcription in a subprocess to avoid fds_to_keep / multiprocessing issues in TUI.

Invoked as: python -m liscribe.transcribe_worker <result_file> <wav_path> <model> <output_dir> <notes_json_path> <speaker_mode>

Writes to result_file: OK:<md_path> or ERROR:<message>
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from liscribe.config import load_config
from liscribe.notes import Note
from liscribe.output import save_transcript, copy_to_clipboard, cleanup_audio
from liscribe.transcriber import (
    load_model,
    transcribe,
    is_model_available,
    build_merged_transcription_result,
)


def _notes_from_json(path: str) -> list[Note]:
    if not path or path == "none":
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Note(index=o["index"], text=o["text"], timestamp=o["timestamp"]) for o in data]


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


def main() -> None:
    if len(sys.argv) < 7:
        print("Usage: transcribe_worker <result_file> <wav_path> <model> <output_dir> <notes_json> <speaker>", file=sys.stderr)
        sys.exit(1)

    result_file = Path(sys.argv[1])
    wav_path = Path(sys.argv[2])
    model_size = sys.argv[3]
    output_dir_arg = sys.argv[4]
    notes_path = sys.argv[5]
    speaker_mode = sys.argv[6].lower() == "true"

    def write_error(msg: str) -> None:
        result_file.write_text(f"ERROR:{msg}", encoding="utf-8")

    if not wav_path.exists():
        write_error(f"Audio file not found: {wav_path}")
        sys.exit(1)

    if not is_model_available(model_size):
        write_error(f"Model {model_size} not installed. Run rec setup to download.")
        sys.exit(1)

    try:
        notes = _notes_from_json(notes_path)
    except Exception as e:
        write_error(f"Notes: {e}")
        sys.exit(1)

    output_dir = Path(output_dir_arg).expanduser().resolve() if output_dir_arg and output_dir_arg.lower() != "none" else None

    dual_session = _load_dual_source_session(wav_path)
    cfg = load_config()
    group_consecutive = bool(cfg.get("group_consecutive_speaker_lines", False))
    suppress_mic_bleed = bool(cfg.get("suppress_mic_bleed_duplicates", True))
    bleed_similarity_threshold = float(cfg.get("mic_bleed_similarity_threshold", 0.62))

    progress_start = time.perf_counter()

    def emit_progress(progress: float, stage: str, info: dict | None = None) -> None:
        progress = max(0.0, min(1.0, float(progress)))
        elapsed = max(0.0, time.perf_counter() - progress_start)
        eta_remaining = (elapsed * (1.0 - progress) / progress) if progress > 0 else None
        payload = {
            "progress": progress,
            "stage": stage,
            "elapsed_sec": elapsed,
            "eta_remaining_sec": eta_remaining,
        }
        if info:
            payload.update({
                "segment_index": info.get("segment_index"),
                "total_estimated": info.get("total_estimated"),
            })
        print(f"PROGRESS:{json.dumps(payload, separators=(',', ':'))}", flush=True)

    emit_progress(0.0, "loading-model")

    try:
        model = load_model(model_size)
        if dual_session:
            def mic_progress(p: float, info: dict | None = None) -> None:
                emit_progress(p * 0.5, "transcribing-mic", info)

            def speaker_progress(p: float, info: dict | None = None) -> None:
                emit_progress(0.5 + (p * 0.5), "transcribing-speaker", info)

            mic_result = transcribe(
                str(dual_session["mic_audio_path"]),
                model=model,
                model_size=model_size,
                on_progress=mic_progress,
            )
            speaker_result = transcribe(
                str(dual_session["speaker_audio_path"]),
                model=model,
                model_size=model_size,
                on_progress=speaker_progress,
            )
            result = build_merged_transcription_result(
                mic_result=mic_result,
                speaker_result=speaker_result,
                speaker_offset_seconds=float(dual_session["speaker_offset_seconds"]),
                group_consecutive=group_consecutive,
                suppress_mic_bleed_duplicates=suppress_mic_bleed,
                bleed_similarity_threshold=bleed_similarity_threshold,
                model_name=model_size,
            )
        else:
            result = transcribe(
                str(wav_path),
                model=model,
                model_size=model_size,
                on_progress=lambda p, info=None: emit_progress(p, "transcribing", info),
            )
        emit_progress(1.0, "saving")
    except Exception as e:
        write_error(str(e))
        sys.exit(1)

    try:
        md_path = save_transcript(
            result=result,
            audio_path=dual_session["mic_audio_path"] if dual_session else wav_path,
            notes=notes or None,
            mic_name="TUI",
            speaker_mode=speaker_mode or bool(dual_session),
            model_name=model_size,
            include_model_in_filename=False,
            output_dir=output_dir,
            filename_stem=dual_session["session_dir"].name if dual_session else None,
        )
    except Exception as e:
        write_error(str(e))
        sys.exit(1)

    if cfg.get("auto_clipboard", False):
        try:
            copy_to_clipboard(result.text)
        except Exception:
            pass

    all_md_paths = [md_path]
    if dual_session:
        cleanup_audio(dual_session["mic_audio_path"], all_md_paths)
        cleanup_audio(dual_session["speaker_audio_path"], all_md_paths)
        try:
            Path(dual_session["session_json_path"]).unlink(missing_ok=True)
        except OSError:
            pass
    else:
        cleanup_audio(wav_path, all_md_paths)

    result_file.write_text(f"OK:{md_path}", encoding="utf-8")


if __name__ == "__main__":
    main()
