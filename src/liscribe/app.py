from __future__ import annotations

from pathlib import Path

from textual.app import App

from liscribe.config import load_config
from liscribe.screens.home import (
    HomePreferencesRequest,
    HomeRecordRequest,
    HomeScreen,
    HomeTranscriptsRequest,
)
from liscribe.screens.devices_screen import DevicesScreen
from liscribe.screens.help_screen import HelpScreen
from liscribe.screens.preferences import PreferencesHubScreen
from liscribe.screens.transcripts import TranscriptsScreen
from liscribe.screens.modals import ConfirmCancelScreen, MicSelectScreen
from liscribe.screens.recording import RecordingResult, RecordingScreen
from liscribe.screens.transcribing import TranscribingScreen


class LiscribeApp(App[None]):
    """TUI shell: Home, Record, Preferences, Transcripts, Help, Devices. CLI launches this."""

    ENABLE_COMMAND_PALETTE = False
    CSS_PATH = "rec.css"

    def __init__(
        self,
        land_on: str = "home",
        folder: str | None = None,
        speaker: bool = False,
        mic: str | None = None,
        prog_name: str = "rec",
    ) -> None:
        super().__init__()
        self._land_on = land_on
        self._folder = folder
        self._speaker = speaker
        self._mic = mic
        self._prog_name = prog_name

    def on_mount(self) -> None:
        try:
            self.theme = "tokyo_night"
        except Exception:
            pass
        if self._land_on == "record" and self._folder:
            self.push_screen(
                RecordingScreen(
                    folder=self._folder,
                    speaker=self._speaker,
                    mic=self._mic,
                    prog_name=self._prog_name,
                ),
                self._on_recording_done,
            )
        elif self._land_on == "preferences":
            self.push_screen(PreferencesHubScreen())
        elif self._land_on == "help":
            self.push_screen(HelpScreen())
        elif self._land_on == "devices":
            self.push_screen(DevicesScreen())
        else:
            self.push_screen(HomeScreen())

    def _on_recording_done(self, result: RecordingResult) -> None:
        """After Recording screen dismisses: show Transcribing then Home, or just Home if cancelled."""
        if result is None:
            self.push_screen(HomeScreen())
            return
        wav_path, notes = result
        wav_path_obj = Path(wav_path)
        dual_source_mode = (
            wav_path_obj.name.lower() == "mic.wav"
            and (wav_path_obj.parent / "speaker.wav").exists()
            and (wav_path_obj.parent / "session.json").exists()
        )
        if self._folder:
            output_dir = self._folder
        elif dual_source_mode:
            output_dir = str(wav_path_obj.parent.parent)
        else:
            output_dir = str(wav_path_obj.parent)
        self.push_screen(
            TranscribingScreen(
                wav_path=wav_path,
                notes=notes,
                output_dir=output_dir,
                speaker_mode=self._speaker or dual_source_mode,
            ),
            self._on_transcribing_done,
        )

    def _on_transcribing_done(self, _: None) -> None:
        self.push_screen(HomeScreen())

    def on_home_record_request(self, _: HomeRecordRequest) -> None:
        folder = self._folder
        if not folder:
            cfg = load_config()
            if bool(cfg.get("record_here_by_default", False)):
                folder = str(Path.cwd() / "docs" / "transcripts")
            else:
                folder = cfg.get("save_folder", "~/transcripts")
        Path(folder).expanduser().resolve().mkdir(parents=True, exist_ok=True)
        self.push_screen(
            RecordingScreen(
                folder=folder,
                speaker=self._speaker,
                mic=self._mic,
                prog_name=self._prog_name,
            ),
            self._on_recording_done,
        )

    def on_home_preferences_request(self, _: HomePreferencesRequest) -> None:
        self.push_screen(PreferencesHubScreen())

    def on_home_transcripts_request(self, _: HomeTranscriptsRequest) -> None:
        self.push_screen(TranscriptsScreen())
