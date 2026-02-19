"""Run transcription in a subprocess to avoid fds_to_keep / multiprocessing issues in TUI.

Invoked as: python -m liscribe.transcribe_worker <result_file> <wav_path> <model> <output_dir> <notes_json_path> <speaker_mode>

Writes to result_file: OK:<md_path> or ERROR:<message>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from liscribe.config import load_config
from liscribe.notes import Note
from liscribe.output import save_transcript, copy_to_clipboard, cleanup_audio
from liscribe.transcriber import load_model, transcribe, is_model_available


def _notes_from_json(path: str) -> list[Note]:
    if not path or path == "none":
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Note(index=o["index"], text=o["text"], timestamp=o["timestamp"]) for o in data]


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

    try:
        model = load_model(model_size)
        result = transcribe(str(wav_path), model=model, model_size=model_size)
    except Exception as e:
        write_error(str(e))
        sys.exit(1)

    try:
        md_path = save_transcript(
            result=result,
            audio_path=wav_path,
            notes=notes or None,
            mic_name="TUI",
            speaker_mode=speaker_mode,
            model_name=model_size,
            include_model_in_filename=False,
            output_dir=output_dir,
        )
    except Exception as e:
        write_error(str(e))
        sys.exit(1)

    cfg = load_config()
    if cfg.get("auto_clipboard", False):
        try:
            copy_to_clipboard(result.text)
        except Exception:
            pass

    all_md_paths = [md_path]
    cleanup_audio(wav_path, all_md_paths)

    result_file.write_text(f"OK:{md_path}", encoding="utf-8")


if __name__ == "__main__":
    main()
