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
            yield TopBar(variant="compact", section="Preferences")
            with Vertical(classes="screen-body"):
                yield Static("")
                yield Button("General", id="btn-general", classes="btn btn-secondary btn-block")
                yield Button("Microphone", id="btn-microphone", classes="btn btn-secondary btn-block")
                yield Button("Transcripts", id="btn-transcripts", classes="btn btn-secondary btn-block")
                yield Button("Whisper", id="btn-whisper", classes="btn btn-secondary btn-block")
                yield Button("Dictation", id="btn-dictation", classes="btn btn-secondary btn-block")
                yield Button("Dependencies", id="btn-deps", classes="btn btn-secondary btn-block")
            with Horizontal(classes="footer-container"):
                yield Static("", classes="spacer-x")
                yield Button("^c Back home", id="btn-back", classes="btn btn-secondary btn-inline fixed-width")


    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-back":
            self.action_back()
        elif bid == "btn-general":
            from liscribe.screens.prefs_general import PrefsGeneralScreen
            self.app.push_screen(PrefsGeneralScreen())
        elif bid == "btn-microphone":
            from liscribe.screens.prefs_microphone import PrefsMicrophoneScreen
            self.app.push_screen(PrefsMicrophoneScreen())
        elif bid == "btn-transcripts":
            from liscribe.screens.prefs_transcripts import PrefsTranscriptsScreen
            self.app.push_screen(PrefsTranscriptsScreen())
        elif bid == "btn-deps":
            from liscribe.screens.prefs_dependencies import PrefsDependenciesScreen
            self.app.push_screen(PrefsDependenciesScreen())
        elif bid == "btn-whisper":
            from liscribe.screens.prefs_whisper import PrefsWhisperScreen
            self.app.push_screen(PrefsWhisperScreen())
        elif bid == "btn-dictation":
            from liscribe.screens.prefs_dictation import PrefsDictationScreen
            self.app.push_screen(PrefsDictationScreen())
