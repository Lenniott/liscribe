"""Home screen — Record, Preferences, Transcripts, Quit."""

from __future__ import annotations

from textual.containers import Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Static

from liscribe.screens.base import HOME_BINDINGS


class HomeRecordRequest(Message):
    """User requested Record from Home."""


class HomePreferencesRequest(Message):
    """User requested Preferences from Home."""


class HomeTranscriptsRequest(Message):
    """User requested Transcripts from Home."""


class HomeScreen(Screen[None]):
    """Home hub: Record, Preferences, Transcripts, Quit."""

    BINDINGS = HOME_BINDINGS

    def compose(self):
        with Vertical(id="home-frame"):
            yield Static("liscribe", id="home-title")
            yield Static("Listen & transcribe locally", id="home-subtitle")
            yield Button("^r  Record", id="btn-record")
            yield Button("^p  Preferences", id="btn-preferences")
            yield Button("^t  Transcripts", id="btn-transcripts")
            yield Static("", id="home-spacer")
            yield Static("^c  Quit", id="home-quit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-record":
            self.action_record()
        elif bid == "btn-preferences":
            self.action_preferences()
        elif bid == "btn-transcripts":
            self.action_transcripts()

    def action_record(self) -> None:
        self.post_message(HomeRecordRequest())

    def action_preferences(self) -> None:
        self.post_message(HomePreferencesRequest())

    def action_transcripts(self) -> None:
        self.post_message(HomeTranscriptsRequest())

    def action_quit(self) -> None:
        self.app.exit()
