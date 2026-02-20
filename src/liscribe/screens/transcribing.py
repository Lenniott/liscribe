"""Transcribing screen — shown after recording saves; runs pipeline in subprocess then Back to Home."""

from __future__ import annotations

import json
import shlex
import select
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from textual import events
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
        self._progress = 0.0
        self._elapsed_sec = 0.0
        self._eta_remaining_sec: float | None = None
        self._stage_text = "Preparing"
        self._model_size = "—"
        self._transcript_name = self._guess_transcript_name()

    def compose(self):
        with Vertical(classes="screen-frame"):
            with Horizontal(classes="top-bar compact"):
                yield Static("liscribe", classes="brand")
                yield Static("transcription", classes="top-bar-section")
            with Vertical(classes="screen-body"):
                yield Static("Transcribing", id="transcribing-title", classes="screen-body-title")
                with Horizontal(id="transcribing-over", classes="row"):
                    yield Static("Preparing", id="transcribing-stage")
                    yield Static(self._transcript_name, id="transcribing-file")
                yield Static("", id="transcribing-blocks")
                with Horizontal(id="transcribing-under", classes="row"):
                    yield Static("0%", id="transcribing-percent")
                    yield Static("--:--:--", id="transcribing-time")
                yield Static("", classes="spacer")
            with Horizontal(id="transcribing-footer", classes="screen-body-footer"):
                yield Button("Open transcript", id="btn-open-transcript", classes="btn primary inline hug-row", disabled=True)
                yield Static("", classes="row-spacer")
                yield Button("esc Back to home", id="btn-back", classes="btn secondary inline hug-row", disabled=True)

    def on_mount(self) -> None:
        self._render_progress()
        self.run_worker(self._run_pipeline, exclusive=True, thread=True)

    def on_resize(self, _: events.Resize) -> None:
        self._render_progress()

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
        self.app.call_from_thread(self._set_model_size, model_size)

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
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            if proc.stdout is not None:
                start = time.monotonic()
                while True:
                    if time.monotonic() - start > 3600:
                        proc.kill()
                        raise subprocess.TimeoutExpired(cmd, 3600)

                    ready, _, _ = select.select([proc.stdout], [], [], 0.2)
                    if ready:
                        line = proc.stdout.readline()
                        if line:
                            self._handle_worker_line(line.strip())

                    if proc.poll() is not None:
                        break

                for line in proc.stdout:
                    if line:
                        self._handle_worker_line(line.strip())

            raw = Path(result_path).read_text(encoding="utf-8").strip()
            if raw.startswith("OK:"):
                self._saved_md = raw[3:].strip()
            elif not raw:
                self._error = "Transcription worker failed."
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

    def _set_model_size(self, model_size: str) -> None:
        self._model_size = model_size
        self._render_progress()

    def _handle_worker_line(self, line: str) -> None:
        if not line.startswith("PROGRESS:"):
            return
        try:
            payload = json.loads(line.split("PROGRESS:", 1)[1].strip())
        except Exception:
            return
        self.app.call_from_thread(self._update_progress, payload)

    def _update_progress(self, payload: dict) -> None:
        stage = str(payload.get("stage") or "transcribing")
        stage_text = {
            "loading-model": "Loading model",
            "transcribing": "Transcribing",
            "transcribing-mic": "Transcribing mic",
            "transcribing-speaker": "Transcribing speaker",
            "saving": "Saving transcript",
        }.get(stage, "Transcribing")
        self._stage_text = stage_text
        self._progress = max(0.0, min(1.0, float(payload.get("progress", 0.0))))
        self._elapsed_sec = max(0.0, float(payload.get("elapsed_sec", self._elapsed_sec) or 0.0))
        eta = payload.get("eta_remaining_sec")
        self._eta_remaining_sec = float(eta) if eta is not None else None
        self._render_progress()

    def _build_blocks_line(self) -> str:
        try:
            width = self.query_one("#transcribing-blocks", Static).size.width
        except Exception:
            width = 48
        total_blocks = max(12, width)
        filled = max(0, min(total_blocks, int(round(self._progress * total_blocks))))
        empty = total_blocks - filled
        return f"[#f4a100]{'█' * filled}[/][#4f5660]{'▒' * empty}[/]"

    @staticmethod
    def _format_clock(value: float | None) -> str:
        if value is None:
            return "--:--:--"
        total = max(0, int(round(float(value))))
        hours, rem = divmod(total, 3600)
        mins, secs = divmod(rem, 60)
        return f"{hours:02d}:{mins:02d}:{secs:02d}"

    def _render_progress(self) -> None:
        try:
            model_suffix = f" ({self._model_size})" if self._model_size != "—" else ""
            stage_label = f"{self._stage_text}{model_suffix}"
            pct = int(round(self._progress * 100))
            right_time = self._elapsed_sec if self._done else self._eta_remaining_sec
            self.query_one("#transcribing-stage", Static).update(stage_label)
            self.query_one("#transcribing-file", Static).update(self._transcript_name)
            self.query_one("#transcribing-blocks", Static).update(self._build_blocks_line())
            self.query_one("#transcribing-percent", Static).update(f"{pct}%")
            self.query_one("#transcribing-time", Static).update(self._format_clock(right_time))
        except Exception:
            pass

    def _update_done(self) -> None:
        self._done = True
        try:
            title = self.query_one("#transcribing-title", Static)
            if self._error:
                title.update("Transcription failed")
                self._stage_text = "Failed"
                self.notify(self._error, severity="error")
            else:
                title.update("Done")
                self._stage_text = "Saved"
                self._progress = 1.0
                self._eta_remaining_sec = 0.0
                if self._saved_md:
                    self._transcript_name = Path(self._saved_md).name
                    self.query_one("#btn-open-transcript", Button).disabled = False
                self.notify(f"Saved: {self._transcript_name}")
            self.query_one("#btn-back", Button).disabled = False
            self._render_progress()
        except Exception:
            pass

    @staticmethod
    def _guess_open_command(app_value: str, transcript_path: Path) -> list[str]:
        app = (app_value or "").strip()
        if not app:
            app = "code"
        if app.lower() in {"default", "system"}:
            if sys.platform == "darwin":
                return ["open", str(transcript_path)]
            if sys.platform.startswith("win"):
                return ["cmd", "/c", "start", "", str(transcript_path)]
            return ["xdg-open", str(transcript_path)]
        return [*shlex.split(app), str(transcript_path)]

    def _guess_transcript_name(self) -> str:
        wav_path_obj = Path(self._wav_path)
        if wav_path_obj.name.lower() == "mic.wav":
            speaker_path = wav_path_obj.parent / "speaker.wav"
            session_json = wav_path_obj.parent / "session.json"
            if speaker_path.exists() and session_json.exists():
                return f"{wav_path_obj.parent.name}.md"
        return f"{wav_path_obj.stem}.md"

    def _open_transcript(self) -> None:
        if not self._saved_md:
            self.notify("Transcript not saved yet.", severity="warning")
            return
        transcript_path = Path(self._saved_md).expanduser().resolve()
        if not transcript_path.exists():
            self.notify(f"Transcript not found: {transcript_path.name}", severity="error")
            return

        cfg = load_config()
        app_value = str(cfg.get("open_transcript_app", "code") or "code")
        try:
            cmd = self._guess_open_command(app_value, transcript_path)
        except ValueError:
            self.notify("Invalid open_transcript_app command.", severity="error")
            return
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.notify(f"Opened with {app_value}: {transcript_path.name}")
        except FileNotFoundError:
            self.notify(f"Open command not found: {app_value}", severity="error")
        except Exception as exc:
            self.notify(f"Could not open transcript: {exc}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-open-transcript":
            self._open_transcript()
        elif event.button.id == "btn-back":
            self.dismiss(None)
