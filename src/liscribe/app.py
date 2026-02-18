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
│  Ctrl+S stop & save  |  Ctrl+P palette           │
│  Ctrl+C cancel                               │
└─────────────────────────────────────────────┘
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import sounddevice as sd
from textual import work
from textual.app import App, ComposeResult, get_system_commands_provider
from textual.binding import Binding
from textual.command import DiscoveryHit, Hit, Provider
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Input, Label, Footer, Header, OptionList
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


class LiscribeCommandsProvider(Provider):
    """Command palette provider for liscribe actions (e.g. Change microphone)."""

    async def search(self, query: str):
        matcher = self.matcher(query)
        if (score := matcher.match("Change microphone")) > 0:
            app = self.app
            yield Hit(
                score,
                matcher.highlight("Change microphone"),
                lambda app=app: app.action_change_mic(),
                help="Open mic selector",
            )

    async def discover(self):
        app = self.app
        yield DiscoveryHit(
            "Change microphone",
            lambda app=app: app.action_change_mic(),
            help="Open mic selector",
        )


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


class RecordingApp(App[str | None]):
    """Main recording TUI application."""

    COMMANDS = App.COMMANDS | {LiscribeCommandsProvider}

    CSS = """
    #status-bar {
        dock: top;
        height: 1;
        background: $accent;
        color: $text;
        padding: 0 1;
    }

    #mic-bar {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }

    #waveform {
        height: 3;
        padding: 0 1;
        background: $surface;
    }

    #notes-container {
        height: 1fr;
        padding: 0 1;
    }

    #notes-log {
        height: 1fr;
        overflow-y: auto;
    }

    #note-input {
        dock: bottom;
        margin-top: 1;
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
        Binding("ctrl+s", "stop_save", "Stop & Save"),
        Binding("ctrl+c", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        folder: str,
        speaker: bool = False,
        mic: str | None = None,
    ):
        super().__init__()
        self.folder = folder
        self.speaker = speaker
        self.mic_arg = mic
        self.session: RecordingSession | None = None
        self.waveform = WaveformMonitor()
        self._note_collection = NoteCollection()
        self._start_time: float = 0.0
        self._saved_path: str | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="status-bar")
        yield Static("Mic: —", id="mic-bar")
        yield Static("", id="waveform")
        yield Vertical(
            Static("", id="notes-log"),
            Input(placeholder="Type a note, press Enter...", id="note-input"),
            id="notes-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._start_recording()
        self.set_interval(0.1, self._update_display)

    def _start_recording(self) -> None:
        """Initialize and start the recording session."""
        self.session = RecordingSession(
            folder=self.folder,
            speaker=self.speaker,
            mic=self.mic_arg,
        )

        cfg = load_config()

        # Resolve mic
        try:
            self.session.device_idx = resolve_device(self.mic_arg)
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            self.exit(None)
            return

        # Speaker setup
        if self.speaker:
            self.session.blackhole_idx = _find_blackhole_device(self.session.blackhole_name)
            if self.session.blackhole_idx is None:
                self.notify(
                    f"BlackHole '{self.session.blackhole_name}' not found. Run 'rec setup'.",
                    severity="error",
                )
                self.exit(None)
                return

            self.session._original_output = get_current_output_device()
            if not set_output_device(self.session.speaker_device_name):
                self.notify(
                    f"Could not switch to '{self.session.speaker_device_name}'. Run 'rec setup'.",
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

        # Start streams
        try:
            self.session._mic_stream = self.session._open_mic_stream(self.session.device_idx)
            if self.speaker and self.session.blackhole_idx is not None:
                self.session._speaker_stream = self.session._open_speaker_stream(self.session.blackhole_idx)
        except Exception as exc:
            self.notify(f"Error starting recording: {exc}", severity="error")
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
        self.query_one("#status-bar", Static).update(status)
        self.query_one("#mic-bar", Static).update(f"Mic: {dev_name}")

        waveform_str = self.waveform.render()
        self.query_one("#waveform", Static).update(f"  {waveform_str}")

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

    def action_change_mic(self) -> None:
        """Open mic selector (used by command palette)."""
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
        """Cancel recording without saving."""
        if self.session:
            # Stop streams without saving
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
