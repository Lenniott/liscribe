"""Home screen — Record, Preferences, Transcripts, Quit."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Static

from pyfiglet import Figlet

from liscribe import __version__
from liscribe.screens.base import HOME_BINDINGS


def _render_brand() -> str:
    """Render home brand title as ASCII art."""
    try:
        return Figlet(font="banner3").renderText("liscribe").rstrip()
    except Exception:
        return "liscribe"


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
        with Vertical(classes="screen-frame"):
            with Vertical(classes="top-bar hero"):
                with Horizontal(classes="version-row"):
                    yield Static(f"v{__version__}", classes="version home-version")
                with Horizontal(classes="title-row"):
                    yield Static(_render_brand(), classes="brand home-brand")
                with Horizontal(classes="subtitle-row"):
                    yield Static("Listen & transcribe locally", classes="tagline home-tagline")
            with Horizontal(classes="screen-body"):
                yield Button("^r  Record", id="btn-record", classes="btn primary")
            with Horizontal(classes="screen-body-footer"):
                yield Button("^t  Transcripts", id="btn-transcripts", classes="btn secondary inline")
                yield Static("", classes="row-spacer")
                yield Button("^p  Preferences", id="btn-preferences", classes="btn secondary inline")               
                yield Static("", classes="row-spacer")
                yield Button("^c  Quit", id="btn-quit", classes="btn danger inline")

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

    def action_quit(self) -> None:
        self.app.exit()
