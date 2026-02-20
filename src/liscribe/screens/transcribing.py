"""Transcribing screen — shown after recording saves; runs pipeline in subprocess then Back to Home."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Static

from liscribe.config import load_config
from liscribe.notes import Note
from liscribe.transcriber import is_model_available


class TranscribingScreen(Screen[None]):
    """Run transcription on the saved WAV in a subprocess (avoids fds_to_keep in TUI), then Done and Back to Home."""

    def __init__(
        self,
        wav_path: str,
        notes: list[Note],
        output_dir: str | None = None,
        speaker_mode: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._wav_path = wav_path
        self._notes = notes
        self._output_dir = Path(output_dir).expanduser().resolve() if output_dir else None
        self._speaker_mode = speaker_mode
        self._done = False
        self._error: str | None = None
        self._saved_md: str | None = None

    def compose(self):
        with Vertical(classes="screen-frame"):
            with Horizontal(classes="top-bar compact"):
                yield Static("liscribe", classes="brand")
                yield Static("Transcribing", classes="top-bar-section")
            with Vertical(classes="screen-body"):
                yield Static("Transcribing…", id="transcribing-title", classes="screen-body-title")
                yield Static("Model: —", id="transcribing-status")
                yield Static("", id="transcribing-progress", classes="screen-body-subtitle")
                yield Static("", classes="spacer")
                yield Button("Back to Home", id="btn-back", classes="btn secondary", disabled=True)

    def on_mount(self) -> None:
        self.run_worker(self._run_pipeline, exclusive=True, thread=True)

    def _run_pipeline(self) -> None:
        """Run transcription in a subprocess to avoid fds_to_keep / multiprocessing issues."""
        cfg = load_config()
        model_size = cfg.get("whisper_model", "base")
        available = [m for m in [model_size] if is_model_available(m)]
        if not available:
            self._error = "No whisper model installed. Run rec setup to download."
            self.app.call_from_thread(self._update_done)
            return

        model_size = available[0]
        self.app.call_from_thread(self._update_status, f"Model: {model_size}")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as nf:
            notes_path = nf.name
            json.dump(
                [{"index": n.index, "text": n.text, "timestamp": n.timestamp} for n in (self._notes or [])],
                nf,
            )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".result", delete=False) as rf:
            result_path = rf.name

        try:
            out_dir = str(self._output_dir) if self._output_dir else "none"
            cmd = [
                sys.executable,
                "-m",
                "liscribe.transcribe_worker",
                result_path,
                self._wav_path,
                model_size,
                out_dir,
                notes_path,
                "true" if self._speaker_mode else "false",
            ]
            subprocess.run(cmd, capture_output=True, timeout=3600, check=False)
            raw = Path(result_path).read_text(encoding="utf-8").strip()
            if raw.startswith("OK:"):
                self._saved_md = raw[3:].strip()
            else:
                self._error = raw[6:].strip() if raw.startswith("ERROR:") else raw
        except subprocess.TimeoutExpired:
            self._error = "Transcription timed out."
        except Exception as e:
            self._error = str(e)
        finally:
            Path(notes_path).unlink(missing_ok=True)
            Path(result_path).unlink(missing_ok=True)

        self.app.call_from_thread(self._update_done)

    def _update_status(self, text: str) -> None:
        try:
            self.query_one("#transcribing-status", Static).update(text)
        except Exception:
            pass

    def _update_done(self) -> None:
        self._done = True
        try:
            title = self.query_one("#transcribing-title", Static)
            status = self.query_one("#transcribing-status", Static)
            if self._error:
                title.update("Transcription failed")
                status.update(self._error)
            else:
                title.update("Done")
                status.update(f"Saved: {Path(self._saved_md or '').name}" if self._saved_md else "Saved")
            self.query_one("#btn-back", Button).disabled = False
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.dismiss(None)
