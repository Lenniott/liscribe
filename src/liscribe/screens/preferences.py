"""Preferences hub — General, Transcripts, Whisper, Dependencies."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from liscribe.screens.base import BackScreen, __version__, render_brand


class PreferencesHubScreen(BackScreen):
    """Preferences menu: four grouped sections, Back to Home."""

    def compose(self):
        with Vertical(classes="screen-frame"):
            with Vertical(classes="top-bar hero"):
                with Horizontal(classes="row"):
                    yield Static(f"v{__version__}", classes="version")
                    yield Static("", classes="spacer-row")
                    yield Static("Preferences", classes="top-bar-section")
                with Horizontal(classes="title-row"):
                    yield Static(render_brand(), classes="brand home-brand")
                with Horizontal(classes="subtitle-row"):
                    yield Static("It listens & transcribes locally", classes="tagline home-tagline")
            with Vertical(classes="screen-body"):
                yield Static("", classes="spacer")  
                with Horizontal(classes="row"):
                    yield Button("General", id="btn-general", classes="btn secondary inline hug-row")
                    yield Static("", classes="spacer-row")
                    yield Button("Transcripts", id="btn-transcripts", classes="btn secondary inline hug-row")
                    yield Static("", classes="spacer-row")
                    yield Button("Whisper", id="btn-whisper", classes="btn secondary inline hug-row")
                    yield Static("", classes="spacer-row")
                    yield Button("Dependencies", id="btn-deps", classes="btn secondary inline hug-row")
                yield Static("", classes="margin-small")                
            with Horizontal(classes="screen-body-footer"):
                yield Button("^c Back to home", id="btn-back", classes="btn secondary inline hug-row")
                yield Static("", classes="spacer-row")  


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
