"""Home screen — Record, Preferences, Transcripts, Quit."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Static

from liscribe.screens.base import HOME_BINDINGS
from liscribe.screens.top_bar import TopBar


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
        with ScrollableContainer(classes="container-frame"):
            with Vertical(classes="screen-frame"):
                yield TopBar(variant="hero", section="Home")
                with Vertical(classes="screen-body"):
                    yield Static("", classes="spacer")
                    yield Button("^r  Record", id="btn-record", classes="btn primary")
                    yield Static("")
                with Horizontal(classes="screen-body-footer"):
                    yield Button("^t  Transcripts", id="btn-transcripts", classes="btn secondary inline")
                    yield Static("", classes="spacer-row")
                    yield Button("^p  Preferences", id="btn-preferences", classes="btn secondary inline")               
                    yield Static("", classes="spacer-row")
                    yield Button("^c  Close", id="btn-quit", classes="btn danger inline")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-record":
            self.action_record()
        elif bid == "btn-preferences":
            self.action_preferences()
        elif bid == "btn-transcripts":
            self.action_transcripts()
        elif bid == "btn-quit":
            self.action_quit()

    def action_record(self) -> None:
        self.post_message(HomeRecordRequest())

    def action_preferences(self) -> None:
        self.post_message(HomePreferencesRequest())

    def action_transcripts(self) -> None:
        self.post_message(HomeTranscriptsRequest())

    def action_home_quit(self) -> None:
        self.action_quit()

    def action_quit(self) -> None:
        self.app.exit()
