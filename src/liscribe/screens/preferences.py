"""Preferences hub — General, Transcripts, Whisper, Dependencies."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from liscribe.screens.base import BackScreen
from liscribe.screens.top_bar import TopBar


class PreferencesHubScreen(BackScreen):
    """Preferences menu: four grouped sections, Back to Home."""

    def compose(self):
        with Vertical(classes="screen-frame"):
            yield TopBar(variant="hero", section="Preferences")
            with Vertical(classes="screen-body"):
                yield Static("", classes="spacer-y")  
                with Horizontal(classes="row"):
                    yield Button("General", id="btn-general", classes="btn btn-secondary btn-inline hug-row")
                    yield Static("", classes="spacer-x")
                    yield Button("Transcripts", id="btn-transcripts", classes="btn btn-secondary btn-inline hug-row")
                    yield Static("", classes="spacer-x")
                    yield Button("Whisper", id="btn-whisper", classes="btn btn-secondary btn-inline hug-row")
                    yield Static("", classes="spacer-x")
                    yield Button("Dependencies", id="btn-deps", classes="btn btn-secondary btn-inline hug-row")
                yield Static("", classes="margin-small")                
            with Horizontal(classes="footer-container"):
                yield Button("^c Back to home", id="btn-back", classes="btn btn-secondary btn-inline hug-row")
                yield Static("", classes="spacer-x")  


    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-back":
            self.action_back()
        elif bid == "btn-general":
            from liscribe.screens.prefs_general import PrefsGeneralScreen
            self.app.push_screen(PrefsGeneralScreen())
        elif bid == "btn-transcripts":
            from liscribe.screens.prefs_transcripts import PrefsTranscriptsScreen
            self.app.push_screen(PrefsTranscriptsScreen())
        elif bid == "btn-deps":
            from liscribe.screens.prefs_dependencies import PrefsDependenciesScreen
            self.app.push_screen(PrefsDependenciesScreen())
        elif bid == "btn-whisper":
            from liscribe.screens.prefs_whisper import PrefsWhisperScreen
            self.app.push_screen(PrefsWhisperScreen())
