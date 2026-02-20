from __future__ import annotations

import time
from typing import Any

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

    BINDINGS = [
        Binding("escape", "no", "No"),
        Binding("y", "yes", "Yes"),
        Binding("n", "no", "No"),
    ]

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

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class RecordingApp(App[str | None]):
    """Main recording TUI application."""

    ENABLE_COMMAND_PALETTE = False

    CSS_PATH = "rec.css"

    BINDINGS = [
        Binding("ctrl+s", "stop_save", "Stop & Save", key_display="^s"),
        Binding("ctrl+c", "cancel", "Cancel", key_display="^C"),
        Binding("ctrl+l", "change_mic", "Change mic", key_display="^l"),
        Binding("ctrl+o", "toggle_speaker", "Toggle speaker", key_display="^o"),
        Binding("ctrl+n", "focus_notes", "Focus notes", key_display="^n"),
        Binding("ctrl+y", "screenshot", "Screenshot", key_display="^y"),
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
        with Vertical(id="app-frame"):
            # Top bar: status + Speaker + Mic
            with Horizontal(id="top-bar"):
                yield Static("", id="status-text")
                with Horizontal(id="top-bar-buttons"):
                    yield Button("^o Speaker", id="btn-speaker")
                    yield Button("^l Mic", id="btn-mic")

            yield Static("Mic: —", id="mic-bar")

            # Waveforms
            with Vertical(id="waveform-container"):
                yield Static("", id="waveform")
                yield Static("Speaker", id="waveform-speaker-label")
                yield Static("", id="waveform-speaker")

            # Notes: scrollable log + input
            with Vertical(id="notes-container"):

                with ScrollableContainer(id="notes-scroll"):
                    yield Static("", id="notes-log")
                yield Static(
                    "Notes are added to the transcript as footnotes.",
                    id="notes-help",
                )
                yield Input(placeholder="Type a note, press Enter...", id="note-input")

            # Footer
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

        # Set speaker label and CSS class
        try:
            speaker_btn = self.query_one("#btn-speaker", Button)
            speaker_btn.label = "^o Speaker ▼" if self.speaker else "^o Speaker ▶"
        except Exception:
            pass

        self.set_class(self.speaker, "waveform-speaker-on")

        try:
            self.query_one("#note-input", Input).focus()
        except Exception:
            pass

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
            self._exit_error_message = str(exc)
            self.notify(str(exc), severity="error")
            self.exit(None)
            return

        # Speaker setup
        if self.speaker:
            self.session.blackhole_idx = _find_blackhole_device(self.session.blackhole_name)
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
        except Exception as exc:
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

        # Waveforms
        wave_widget = self.query_one("#waveform", Static)
        width = wave_widget.size.width or 0
        bar_w = width - 2 if width > 4 else 40

        mic_bar = self.waveform.render(bar_w)
        wave_widget.update(mic_bar)

        if self.speaker:
            try:
                speaker_widget = self.query_one("#waveform-speaker", Static)
                s_width = speaker_widget.size.width or width
                s_bar_w = s_width - 2 if s_width and s_width > 4 else bar_w
                speaker_bar = self.waveform_speaker.render(s_bar_w)
                speaker_widget.update(speaker_bar)
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle top-bar and footer button actions."""
        bid = event.button.id
        if bid == "btn-mic":
            self.action_change_mic()
        elif bid == "btn-speaker":
            self.action_toggle_speaker()
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

    def action_toggle_speaker(self) -> None:
        """Toggle speaker capture via keyboard or button."""
        if self.speaker:
            self.action_remove_speaker_capture()
        else:
            self.action_add_speaker_capture()

    def action_focus_notes(self) -> None:
        """Focus the note input field."""
        try:
            self.query_one("#note-input", Input).focus()
        except Exception:
            pass

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
        self.set_class(True, "waveform-speaker-on")
        try:
            self.query_one("#btn-speaker", Button).label = "^o Speaker ▼"
        except Exception:
            pass
        self.notify("Speaker capture added")

    def action_remove_speaker_capture(self) -> None:
        """Disable speaker capture mid-recording (toggle off)."""
        if not self.session or not self.speaker:
            return
        self.session.disable_speaker_capture()
        self.speaker = False
        self.set_class(False, "waveform-speaker-on")
        try:
            self.query_one("#btn-speaker", Button).label = "^o Speaker ▶"
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
