"""Preferences hub — Dependency check, Alias, Whisper, Save location."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from liscribe.screens.base import BackScreen


class PreferencesHubScreen(BackScreen):
    """Preferences menu: four entries, Back to Home."""

    def compose(self):
        with Vertical(classes="screen-frame"):
            with Horizontal(classes="top-bar compact"):
                yield Static("liscribe", classes="brand")
                yield Static("Preferences", classes="top-bar-section")
            with Vertical(classes="screen-body"):
                yield Button("Dependency check", id="btn-deps", classes="btn secondary")
                yield Button("Alias", id="btn-alias", classes="btn secondary")
                yield Button("Whisper", id="btn-whisper", classes="btn secondary")
                yield Button("Save location", id="btn-save", classes="btn secondary")
                yield Static("", classes="spacer")
                yield Button("Back to Home", id="btn-back", classes="btn secondary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-back":
            self.action_back()
        elif bid == "btn-deps":
            from liscribe.screens.prefs_dependencies import PrefsDependenciesScreen
            self.app.push_screen(PrefsDependenciesScreen())
        elif bid == "btn-alias":
            from liscribe.screens.prefs_alias import PrefsAliasScreen
            self.app.push_screen(PrefsAliasScreen())
        elif bid == "btn-whisper":
            from liscribe.screens.prefs_whisper import PrefsWhisperScreen
            self.app.push_screen(PrefsWhisperScreen())
        elif bid == "btn-save":
            from liscribe.screens.prefs_save_location import PrefsSaveLocationScreen
            self.app.push_screen(PrefsSaveLocationScreen())
