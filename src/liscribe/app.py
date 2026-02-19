"""Textual TUI app for recording sessions.

Layout:
┌─────────────────────────────────────────────┐
│  liscribe  ●  REC  00:01:23                 │
│  Mic: MacBook Pro Microphone                 │
├─────────────────────────────────────────────┤
│  ▁▂▃▅▇▅▃▂▁▂▃▄▅▆▇▆▅▄▃▂▁▂▃▅▇▅▃▂▁           │
├─────────────────────────────────────────────┤
│  Notes:                                      │
│  [1] Remember to follow up on Q3 budget      │
│  > _                                         │
├─────────────────────────────────────────────┤
│  ^s Stop & Save  |  ^C Cancel                 │
└─────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import time
from typing import Any

# #region agent log
_DEBUG_LOG = "/Users/benjamin/Desktop/Scratch/liscribe/.cursor/debug-090741.log"

def _dlog(msg: str, data: dict | None = None, hypothesis_id: str | None = None, location: str = "app.py") -> None:
    with open(_DEBUG_LOG, "a") as f:
        f.write(json.dumps({"sessionId": "090741", "message": msg, "data": data or {}, "hypothesisId": hypothesis_id, "timestamp": int(time.time() * 1000), "location": location}) + "\n")
# #endregion

import numpy as np
import sounddevice as sd
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Static, Input, Label, OptionList, Button
from textual.widgets.option_list import Option

from liscribe.config import load_config
from liscribe.notes import Note, NoteCollection
from liscribe.platform_setup import get_current_output_device, set_output_device
from liscribe.recorder import (
    RecordingSession,
    list_input_devices,
    resolve_device,
    _find_blackhole_device,
)
from liscribe.waveform import WaveformMonitor


class MicSelectScreen(ModalScreen[int | None]):
    """Modal screen to select a different microphone."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, current_device: int | None) -> None:
        super().__init__()
        self.current_device = current_device

    def compose(self) -> ComposeResult:
        devices = list_input_devices()
        options = []
        for dev in devices:
            marker = " ◄" if dev["index"] == self.current_device else ""
            label = f"[{dev['index']}] {dev['name']} ({dev['channels']}ch, {dev['sample_rate']}Hz){marker}"
            options.append(Option(label, id=str(dev["index"])))

        yield Vertical(
            Label("Select microphone:", id="mic-select-title"),
            OptionList(*options, id="mic-list"),
            id="mic-select-container",
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(int(event.option.id))

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmCancelScreen(ModalScreen[bool]):
    """Ask user to confirm discarding the recording."""

    BINDINGS = [Binding("escape", "no", "No")]

    CSS = """
    #cancel-confirm-container {
        width: 55;
        min-width: 50;
        padding: 1 2;
        height: auto;
        margin-top: 1;
        margin-left: 1;
        margin-right: 1;
        margin-bottom: 1;
    }
    #cancel-confirm-message {
        width: 100%;
        margin-bottom: 1;
        text-align: center;
    }
    #cancel-confirm-list {
        min-width: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Discard recording? Unsaved audio will be lost.", id="cancel-confirm-message"),
            OptionList(
                Option("Yes, discard recording", id="yes"),
                Option("No, keep recording", id="no"),
                id="cancel-confirm-list",
            ),
            id="cancel-confirm-container",
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "yes":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_no(self) -> None:
        self.dismiss(False)


class RecordingApp(App[str | None]):
    """Main recording TUI application."""

    ENABLE_COMMAND_PALETTE = False
    # Prefer Tokyo Night theme if available (e.g. from textual-themes); otherwise default.

    CSS = """
    #top-bar {
        width: 100%;
        height: 1;
        padding: 0 1;
        background: $accent;
        color: $text;
        align: left middle;
    }
    #status-text {
        width: 1fr;
    }
    #top-bar-buttons {
        width: auto;
    }

    #top-bar-buttons Button {
        margin-left: 1;
        background: transparent;
        color: $text;
        border: none;
        text-style: bold;
        width: auto;
        max-width: 12;
        min-width: 3;
    }
    #top-bar-buttons Button:hover {
        background: $surface;
        text-style: bold underline;
    }
    #top-bar-buttons Button:focus {
        background: $surface;
        text-style: bold underline;
    }

    #mic-bar {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }

    #waveform, #waveform-speaker {
        height: auto;
        padding: 1;
        background: $surface;
    }

    #notes-container {
        height: 1fr;
        min-height: 5;
        padding: 0 1;
    }

    #notes-help {
        color: $text-muted;
        margin-bottom: 0;
    }

    #notes-scroll {
        height: 1fr;
        min-height: 3;
    }

    #notes-log {
        height: auto;
    }

    #note-input {
        margin-top: 1;
    }

    #footer-bar {
        width: 100%;
        height: 1;
        padding: 0 1;
        align: left middle;
        background: $surface;
        color: $text-muted;
    }
    #footer-bar Button {
        background: transparent;
        color: $text-muted;
        border: none;
    }
    #footer-bar Button:hover {
        background: $background;
        color: $text;
    }
    #footer-bar Button:focus {
        background: $background;
        color: $text;
    }
    #btn-footer-save {
        width: auto;
        align: left middle;
    }
    #footer-bar-spacer {
        width: 1fr;
        min-width: 1;
    }
    #btn-footer-cancel {
        width: auto;
        align: right middle;
    }

    #mic-select-container {
        align: center middle;
        width: 60;
        height: auto;
        min-height: 8;
        max-height: 20;
        background: $surface;
        border: tall $accent;
        padding: 1 2;
    }

    #mic-select-title {
        text-align: center;
        margin-bottom: 1;
    }

    #mic-list {
        height: auto;
        min-height: 3;
        max-height: 15;
    }
    """

    BINDINGS = [
        Binding("ctrl+s", "stop_save", "Stop & Save", key_display="^s"),
        Binding("ctrl+c", "cancel", "Cancel", key_display="^C"),
    ]

    def __init__(
        self,
        folder: str,
        speaker: bool = False,
        mic: str | None = None,
        prog_name: str = "rec",
    ):
        super().__init__()
        self.folder = folder
        self.speaker = speaker
        self.mic_arg = mic
        self.prog_name = prog_name
        self.session: RecordingSession | None = None
        self.waveform = WaveformMonitor()
        self.waveform_speaker = WaveformMonitor()
        self._note_collection = NoteCollection()
        self._start_time: float = 0.0
        self._saved_path: str | None = None
        self._exit_error_message: str | None = None

    def compose(self) -> ComposeResult:
        # Top bar: status + Speaker + Mic (wireframe)
        with Horizontal(id="top-bar"):
            yield Static("", id="status-text")
            with Horizontal(id="top-bar-buttons"):
                yield Button("Speaker", id="btn-speaker")
                yield Button("Mic", id="btn-mic")
        yield Static("Mic: —", id="mic-bar")
        yield Static("", id="waveform")
        if self.speaker:
            yield Static("", id="waveform-speaker")
        # Notes: scrollable log + input
        with Vertical(id="notes-container"):
            yield Static("Notes are added to the transcript as footnotes.", id="notes-help")
            with ScrollableContainer(id="notes-scroll"):
                yield Static("", id="notes-log")
            yield Input(placeholder="Type a note, press Enter...", id="note-input")
        with Horizontal(id="footer-bar"):
            yield Button("^s Stop & Save", id="btn-footer-save")
            yield Static("", id="footer-bar-spacer")
            yield Button("^C Cancel", id="btn-footer-cancel")

    def on_mount(self) -> None:
        try:
            self.theme = "tokyo_night"
        except Exception:
            pass
        self._start_recording()
        self.set_interval(0.1, self._update_display)
        try:
            speaker_btn = self.query_one("#btn-speaker", Button)
            speaker_btn.label = "Speaker on" if self.speaker else "Speaker"
        except Exception:
            pass
        try:
            self.query_one("#note-input", Input).focus()
        except Exception:
            pass

    def _start_recording(self) -> None:
        """Initialize and start the recording session."""
        # #region agent log
        _dlog("_start_recording entry", {"speaker": self.speaker, "mic_arg": self.mic_arg, "folder": self.folder}, "entry", "app.py:_start_recording")
        # #endregion
        self.session = RecordingSession(
            folder=self.folder,
            speaker=self.speaker,
            mic=self.mic_arg,
        )

        cfg = load_config()

        # Resolve mic
        try:
            self.session.device_idx = resolve_device(self.mic_arg)
            # #region agent log
            _dlog("resolve_device ok", {"device_idx": self.session.device_idx}, "C", "app.py:_start_recording")
            # #endregion
        except ValueError as exc:
            # #region agent log
            _dlog("resolve_device ValueError", {"exc": str(exc)}, "C", "app.py:_start_recording")
            # #endregion
            self._exit_error_message = str(exc)
            self.notify(str(exc), severity="error")
            self.exit(None)
            return

        # Speaker setup
        if self.speaker:
            self.session.blackhole_idx = _find_blackhole_device(self.session.blackhole_name)
            # #region agent log
            _dlog("blackhole lookup", {"blackhole_idx": self.session.blackhole_idx, "blackhole_name": self.session.blackhole_name}, "A", "app.py:_start_recording")
            # #endregion
            if self.session.blackhole_idx is None:
                self._exit_error_message = (
                    f"BlackHole '{self.session.blackhole_name}' not found. Run '{self.prog_name} setup'. "
                    "See README: BlackHole Setup."
                )
                self.notify(self._exit_error_message, severity="error")
                self.exit(None)
                return

            self.session._original_output = get_current_output_device()
            set_ok = set_output_device(self.session.speaker_device_name)
            # #region agent log
            _dlog("set_output_device", {"ok": set_ok, "speaker_device_name": self.session.speaker_device_name, "original_output": self.session._original_output}, "B", "app.py:_start_recording")
            # #endregion
            if not set_ok:
                self._exit_error_message = (
                    f"Could not switch to '{self.session.speaker_device_name}'. "
                    f"Run '{self.prog_name} setup'. List output devices: SwitchAudioSource -a -t output. "
                    "See README: BlackHole Setup."
                )
                self.notify(
                    f"Could not switch to '{self.session.speaker_device_name}'. Run '{self.prog_name} setup'. See README: BlackHole Setup.",
                    severity="error",
                )
                self.exit(None)
                return

        # Patch callbacks to also feed waveform
        original_mic_cb = self.session._mic_callback

        def patched_mic_cb(indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
            original_mic_cb(indata, frames, time_info, status)
            self.waveform.push(indata)

        self.session._mic_callback = patched_mic_cb

        if self.speaker:
            original_speaker_cb = self.session._speaker_callback

            def patched_speaker_cb(indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
                original_speaker_cb(indata, frames, time_info, status)
                self.waveform_speaker.push(indata)

            self.session._speaker_callback = patched_speaker_cb

        # Start streams
        try:
            self.session._mic_stream = self.session._open_mic_stream(self.session.device_idx)
            if self.speaker and self.session.blackhole_idx is not None:
                self.session._speaker_stream = self.session._open_speaker_stream(self.session.blackhole_idx)
            # #region agent log
            _dlog("streams opened ok", {}, "D", "app.py:_start_recording")
            # #endregion
        except Exception as exc:
            # #region agent log
            _dlog("stream open exception", {"exc": str(exc), "exc_type": type(exc).__name__}, "D", "app.py:_start_recording")
            # #endregion
            self._exit_error_message = f"Error starting recording: {exc}"
            self.notify(self._exit_error_message, severity="error")
            self.session._restore_audio_output()
            self.exit(None)
            return

        self._start_time = time.time()
        self.session._start_time = self._start_time
        self._note_collection.start_from(self._start_time)

    def _update_display(self) -> None:
        """Update status bar and waveform (called every 100ms)."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        mins, secs = divmod(int(elapsed), 60)
        hrs, mins = divmod(mins, 60)

        # Device name
        if self.session and self.session.device_idx is not None:
            dev_info = sd.query_devices(self.session.device_idx)
            dev_name = dev_info["name"]
        else:
            dev_info = sd.query_devices(sd.default.device[0])
            dev_name = dev_info["name"]

        mode = " + Speaker" if self.speaker else ""
        status = f"  liscribe  ●  REC  {hrs:02d}:{mins:02d}:{secs:02d}{mode}"
        self.query_one("#status-text", Static).update(status)
        self.query_one("#mic-bar", Static).update(f"Mic: {dev_name}")

        # Responsive waveform width: use container width with fallback so bar is always visible
        bar_w = "100%"
        try:
            w = self.query_one("#waveform", Static).content_region.width
            if w is not None and w > 2:
                bar_w = w - 2
        except Exception:
            pass
        mic_bar = self.waveform.render(bar_w)
        self.query_one("#waveform", Static).update(f"  {mic_bar}")
        if self.speaker:
            try:
                speaker_bar = self.waveform_speaker.render(bar_w)
                self.query_one("#waveform-speaker", Static).update(f"  {speaker_bar}")
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle top-bar and footer button actions."""
        bid = event.button.id
        if bid == "btn-mic":
            self.action_change_mic()
        elif bid == "btn-speaker":
            if self.speaker:
                self.action_remove_speaker_capture()
            else:
                self.action_add_speaker_capture()
        elif bid == "btn-footer-save":
            self.action_stop_save()
        elif bid == "btn-footer-cancel":
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle note submission."""
        text = event.value.strip()
        if not text:
            return
        self._note_collection.add(text)
        notes_display = "\n".join(
            f"  [{n.index}] {n.text}" for n in self._note_collection.notes
        )
        self.query_one("#notes-log", Static).update(notes_display)
        event.input.value = ""

    def action_stop_save(self) -> None:
        """Stop recording and save."""
        if self.session:
            path = self.session._stop_and_save()
            self._saved_path = path
        self.exit(self._saved_path)

    def action_add_speaker_capture(self) -> None:
        """Enable speaker capture mid-recording (toggle on)."""
        if not self.session or self.speaker:
            return
        original_speaker_cb = self.session._speaker_callback

        def patched_speaker_cb(indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
            original_speaker_cb(indata, frames, time_info, status)
            self.waveform_speaker.push(indata)

        self.session._speaker_callback = patched_speaker_cb
        err = self.session.enable_speaker_capture()
        if err:
            self.notify(err, severity="error")
            return
        self.speaker = True
        self.mount(Static("", id="waveform-speaker"), before=self.query_one("#notes-container"))
        try:
            self.query_one("#btn-speaker", Button).label = "Speaker on"
        except Exception:
            pass
        self.notify("Speaker capture added")

    def action_remove_speaker_capture(self) -> None:
        """Disable speaker capture mid-recording (toggle off)."""
        if not self.session or not self.speaker:
            return
        if self.session._speaker_stream is not None:
            self.session._speaker_stream.stop()
            self.session._speaker_stream.close()
            self.session._speaker_stream = None
        self.session._restore_audio_output()
        self.speaker = False
        try:
            self.query_one("#waveform-speaker", Static).remove()
        except Exception:
            pass
        try:
            self.query_one("#btn-speaker", Button).label = "Speaker"
        except Exception:
            pass
        self.notify("Speaker capture off")

    def action_change_mic(self) -> None:
        """Open mic selector."""
        current = self.session.device_idx if self.session else None
        self.push_screen(MicSelectScreen(current), self._on_mic_selected)

    def _on_mic_selected(self, device_idx: int | None) -> None:
        if device_idx is not None and self.session:
            self.session.switch_mic(device_idx)
            dev_info = sd.query_devices(device_idx)
            self.notify(f"Switched to: {dev_info['name']}")
        else:
            self.notify("Mic unchanged")

    def action_cancel(self) -> None:
        """Show confirmation modal; if user confirms, discard recording without saving."""
        self.push_screen(ConfirmCancelScreen(), self._on_cancel_confirmed)

    def _on_cancel_confirmed(self, confirmed: bool) -> None:
        if confirmed:
            self._do_cancel()

    def _do_cancel(self) -> None:
        """Stop recording and exit without saving."""
        # #region agent log
        _dlog("_do_cancel called", {"has_session": self.session is not None}, "E", "app.py:_do_cancel")
        # #endregion
        if self.session:
            for stream in (self.session._mic_stream, self.session._speaker_stream):
                if stream is not None:
                    stream.stop()
                    stream.close()
            self.session._mic_stream = None
            self.session._speaker_stream = None
            self.session._restore_audio_output()
        self.exit(None)

    @property
    def notes(self) -> list[Note]:
        return self._note_collection.notes
