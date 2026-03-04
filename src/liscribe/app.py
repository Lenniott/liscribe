from __future__ import annotations

import atexit
import logging
import signal
from pathlib import Path
from typing import Any

from textual.app import App

from liscribe.config import load_config
from liscribe.screens.home import (
    HomePreferencesRequest,
    HomeRecordRequest,
    HomeScreen,
    HomeTranscriptsRequest,
    HomeHelpRequest
)
from liscribe.screens.devices_screen import DevicesScreen
from liscribe.screens.help_screen import HelpScreen
from liscribe.screens.preferences import PreferencesHubScreen
from liscribe.screens.transcripts import TranscriptsScreen
from liscribe.screens.modals import ConfirmCancelScreen, MicSelectScreen
from liscribe.screens.recording import RecordingResult, RecordingScreen
from liscribe.screens.transcribing import TranscribingScreen
from liscribe.screens.help_screen import HelpScreen

logger = logging.getLogger(__name__)


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
        self._emergency_save_triggered = False
        self._original_sigterm = signal.getsignal(signal.SIGTERM)
        self._original_sighup = signal.getsignal(signal.SIGHUP)
        signal.signal(signal.SIGTERM, self._handle_terminate)
        signal.signal(signal.SIGHUP, self._handle_terminate)
        atexit.register(self._atexit_save)

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

    def _handle_terminate(self, signum: int, frame: Any) -> None:
        """Save any in-progress recording on SIGTERM or SIGHUP (e.g. terminal close)."""
        if self._emergency_save_triggered:
            return
        self._emergency_save_triggered = True

        screen = self.screen
        if isinstance(screen, RecordingScreen) and screen.session:
            try:
                self.call_from_thread(screen.action_stop_save)
            except Exception:
                # Event loop may already be shutting down — call directly as fallback
                try:
                    screen.session._stop_and_save()
                except Exception:
                    logger.exception("Emergency save failed during signal %s", signum)

        signal.signal(signal.SIGTERM, self._original_sigterm)
        signal.signal(signal.SIGHUP, self._original_sighup)

    def _atexit_save(self) -> None:
        """Last-resort: save audio still in RAM if signal handler didn't fire."""
        if self._emergency_save_triggered:
            return
        try:
            screen = self.screen
            if isinstance(screen, RecordingScreen) and screen.session:
                if screen.session._mic_chunks:
                    screen.session._stop_and_save()
        except Exception:
            pass

    def on_home_record_request(self, _: HomeRecordRequest) -> None:
        folder = self._folder
        if not folder:
            cfg = load_config()
            if bool(cfg.get("record_here_by_default", False)):
                folder = str(Path.cwd() / "docs" / "transcripts")
            else:
                folder = cfg.get("save_folder", "~/transcripts")
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

    def on_home_help_request(self, _: HomeHelpRequest) -> None:
        self.push_screen(HelpScreen())