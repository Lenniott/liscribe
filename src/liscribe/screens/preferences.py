"""Preferences hub — Dependency check, Alias, Whisper, Save location."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from liscribe.screens.base import BackScreen, __version__, render_brand


class PreferencesHubScreen(BackScreen):
    """Preferences menu: four entries, Back to Home."""

    def compose(self):
        with Vertical(classes="screen-frame"):
            with Vertical(classes="top-bar hero"):
                with Horizontal(classes="row"):
                    yield Static(f"v{__version__}", classes="version")
                    yield Static("", classes="row-spacer")
                    yield Static("Preferences", classes="top-bar-section")
                with Horizontal(classes="title-row"):
                    yield Static(render_brand(), classes="brand home-brand")
                with Horizontal(classes="subtitle-row"):
                    yield Static("It listens & transcribes locally", classes="tagline home-tagline")
            with Vertical(classes="screen-body"):
                with Horizontal(classes="row"):
                    yield Button("Save path", id="btn-save", classes="btn secondary inline hug-row")
                    yield Static("", classes="row-spacer")
                    yield Button("Alias", id="btn-alias", classes="btn secondary inline hug-row")
                    yield Static("", classes="row-spacer")
                    yield Button("Whisper", id="btn-whisper", classes="btn secondary inline hug-row")
                    yield Static("", classes="row-spacer")
                    yield Button("Dependencies", id="btn-deps", classes="btn secondary inline hug-row")
                yield Static("", classes="spacer")                
                with Horizontal(classes="screen-body-footer"):
                    yield Button("esc Back to home", id="btn-back", classes="btn secondary inline hug-row")
                    yield Static("", classes="row-spacer")  


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
