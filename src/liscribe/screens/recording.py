"""Recording screen — waveform, mic, notes, stop/save. Returns (wav_path, notes) or None."""

from __future__ import annotations

import atexit
import time
from typing import Any

import numpy as np
import sounddevice as sd
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Static

from liscribe.config import load_config
from liscribe.screens.top_bar import TopBar
from liscribe.screens.base import RECORDING_BINDINGS
from liscribe.notes import Note, NoteCollection
from liscribe.platform_setup import get_current_output_device, set_output_device
from liscribe.recorder import (
    RecordingSession,
    _find_blackhole_device,
    list_input_devices,
    resolve_device,
)
from liscribe.screens.modals import ConfirmCancelScreen, MicSelectScreen
from liscribe.waveform import WaveformMonitor

# Result when user saves: (wav_path, notes); when cancel: None
RecordingResult = tuple[str, list[Note]] | None


class RecordingScreen(Screen[RecordingResult]):
    """Recording TUI. Dismisses with (wav_path, notes) on save or None if cancelled."""

    BINDINGS = RECORDING_BINDINGS

    def __init__(
        self,
        folder: str,
        speaker: bool = False,
        mic: str | None = None,
        prog_name: str = "rec",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.folder = folder
        self.speaker = speaker
        self.mic_arg = mic
        self.prog_name = prog_name
        self.session: RecordingSession | None = None
        self.waveform = WaveformMonitor()
        self.waveform_speaker = WaveformMonitor()
        self._note_collection = NoteCollection()
        self._start_time: float = 0.0
        self._exit_error_message: str | None = None

    def compose(self):
        with Vertical(classes="screen-frame large-container"):
            with TopBar(variant="hero", section="Recording"):
                yield Static("", id="status-text")
            with Vertical(classes="screen-body large-container"):
                yield Static("Mic: —", id="mic-bar")
                with Vertical(id="waveform-container"):
                    yield Static("", id="waveform")
                    yield Static("Speaker", id="waveform-speaker-label")
                    yield Static("", id="waveform-speaker")
                with Vertical(id="notes-container"):
                    with ScrollableContainer(classes="grow-container"):
                        yield Static("", id="notes-log")
                    yield Static(
                        "Notes are added to the transcript as footnotes.",
                        id="notes-help",
                    )
                    yield Input(placeholder="Type a note, press Enter...", id="note-input")
            with Horizontal(classes="screen-body-footer"):
                yield Button("Save", id="btn-save", classes="btn primary inline hug-row")
                yield Static("", classes="spacer-row")
                yield Button("^o Speaker", id="btn-speaker", classes="btn secondary inline")
                yield Static("", classes="spacer-row")
                yield Button("^l Mic", id="btn-mic", classes="btn secondary inline")
                yield Static("", classes="spacer-row")
                yield Button("^c Cancel", id="btn-back", classes="btn danger inline")



    def on_mount(self) -> None:
        try:
            self.theme = "tokyo_night"
        except Exception:
            pass

        self._start_recording()
        self.set_interval(0.1, self._update_display)

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

        try:
            self.session.device_idx = resolve_device(self.mic_arg)
        except ValueError as exc:
            self._exit_error_message = str(exc)
            self.notify(str(exc), severity="error")
            self.dismiss(None)
            return

        if self.speaker:
            self.session.blackhole_idx = _find_blackhole_device(self.session.blackhole_name)
            if self.session.blackhole_idx is None:
                self._exit_error_message = (
                    f"BlackHole '{self.session.blackhole_name}' not found. Run '{self.prog_name} setup'. "
                    "See README: BlackHole Setup."
                )
                self.notify(self._exit_error_message, severity="error")
                self.dismiss(None)
                return

            self.session._original_output = get_current_output_device()
            set_ok = set_output_device(self.session.speaker_device_name)
            if not set_ok:
                self._exit_error_message = (
                    f"Could not switch to '{self.session.speaker_device_name}'. "
                    f"Run '{self.prog_name} setup'. See README: BlackHole Setup."
                )
                self.notify(self._exit_error_message, severity="error")
                self.dismiss(None)
                return
            atexit.register(self.session._restore_audio_output)

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

        try:
            self.session._mic_stream = self.session._open_mic_stream(self.session.device_idx)
            if self.speaker and self.session.blackhole_idx is not None:
                self.session._speaker_stream = self.session._open_speaker_stream(self.session.blackhole_idx)
        except Exception as exc:
            self._exit_error_message = f"Error starting recording: {exc}"
            self.notify(self._exit_error_message, severity="error")
            self.session._restore_audio_output()
            self.dismiss(None)
            return

        self._start_time = time.time()
        self.session._start_time = self._start_time
        self._note_collection.start_from(self._start_time)

    def _update_display(self) -> None:
        """Update status bar and waveform (called every 100ms)."""
        elapsed = time.time() - self._start_time if self._start_time else 0
        mins, secs = divmod(int(elapsed), 60)
        hrs, mins = divmod(mins, 60)

        if self.session and self.session.device_idx is not None:
            dev_info = sd.query_devices(self.session.device_idx)
            dev_name = dev_info["name"]
        else:
            dev_info = sd.query_devices(sd.default.device[0])
            dev_name = dev_info["name"]

        mode = " + Speaker" if self.speaker else ""
        status = f"●  REC  {hrs:02d}:{mins:02d}:{secs:02d}{mode}"
        try:
            self.query_one(TopBar).status_text = status
        except Exception:
            pass
        self.query_one("#mic-bar", Static).update(f"Mic: {dev_name}")

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
        bid = event.button.id
        if bid == "btn-mic":
            self.action_change_mic()
        elif bid == "btn-speaker":
            self.action_toggle_speaker()
        elif bid == "btn-save":
            self.action_stop_save()
        elif bid == "btn-back":
            self.action_cancel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
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
        if self.session:
            path = self.session._stop_and_save()
            self.dismiss((path, self._note_collection.notes))
        else:
            self.dismiss(None)

    def action_toggle_speaker(self) -> None:
        if self.speaker:
            self.action_remove_speaker_capture()
        else:
            self.action_add_speaker_capture()

    def action_focus_notes(self) -> None:
        try:
            self.query_one("#note-input", Input).focus()
        except Exception:
            pass

    def action_add_speaker_capture(self) -> None:
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
        current = self.session.device_idx if self.session else None
        self.app.push_screen(MicSelectScreen(current), self._on_mic_selected)

    def _on_mic_selected(self, device_idx: int | None) -> None:
        if device_idx is not None and self.session:
            self.session.switch_mic(device_idx)
            dev_info = sd.query_devices(device_idx)
            self.notify(f"Switched to: {dev_info['name']}")
        else:
            self.notify("Mic unchanged")

    def action_cancel(self) -> None:
        self.app.push_screen(ConfirmCancelScreen(), self._on_cancel_confirmed)

    def _on_cancel_confirmed(self, confirmed: bool) -> None:
        if confirmed:
            self._do_cancel()

    def _do_cancel(self) -> None:
        if self.session:
            for stream in (self.session._mic_stream, self.session._speaker_stream):
                if stream is not None:
                    stream.stop()
                    stream.close()
            self.session._mic_stream = None
            self.session._speaker_stream = None
            self.session._restore_audio_output()
        self.dismiss(None)
