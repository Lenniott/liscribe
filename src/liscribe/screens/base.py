"""Shared bindings and base screen for liscribe TUI."""

from __future__ import annotations

from textual.binding import Binding
from textual.screen import Screen


BACK_BINDINGS = [Binding("escape", "back", "Back")]

RECORDING_BINDINGS = [
    Binding("ctrl+s", "stop_save", "Stop & Save", key_display="^s"),
    Binding("ctrl+c", "cancel", "Cancel", key_display="^C"),
    Binding("ctrl+l", "change_mic", "Change mic", key_display="^l"),
    Binding("ctrl+o", "toggle_speaker", "Toggle speaker", key_display="^o"),
    Binding("ctrl+n", "focus_notes", "Focus notes", key_display="^n"),
    Binding("ctrl+y", "screenshot", "Screenshot", key_display="^y"),
]

HOME_BINDINGS = [
    Binding("ctrl+r", "record", "Record", key_display="^r"),
    Binding("ctrl+p", "preferences", "Preferences", key_display="^p"),
    Binding("ctrl+t", "transcripts", "Transcripts", key_display="^t"),
    Binding("ctrl+c", "quit", "Quit", key_display="^c"),
]


class BackScreen(Screen[None]):
    """Screen that provides escape -> back and pushes Home when stack is empty."""

    BINDINGS = BACK_BINDINGS

    def action_back(self) -> None:
        self.app.pop_screen()
        if len(self.app.screen_stack) == 0:
            from liscribe.screens.home import HomeScreen
            self.app.push_screen(HomeScreen())
