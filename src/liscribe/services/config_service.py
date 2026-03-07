"""Singleton wrapper around config.py that provides typed get/set access."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from liscribe import config as _config

logger = logging.getLogger(__name__)


class ConfigService:
    """Single source of config truth for v2.

    Loads once on construction; writes back to disk on every set().
    Callers share one instance created in app.py.
    """

    def __init__(self) -> None:
        _config.init_config_if_missing()
        self._values: dict[str, Any] = _config.load_config()

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value
        _config.save_config(self._values)

    def reload(self) -> None:
        """Re-read config from disk (e.g. after external edit)."""
        self._values = _config.load_config()

    # ------------------------------------------------------------------
    # Typed convenience accessors
    # ------------------------------------------------------------------

    @property
    def save_folder(self) -> str:
        return str(self._values.get("save_folder", "~/transcripts"))

    @save_folder.setter
    def save_folder(self, path: str) -> None:
        self.set("save_folder", path)

    @property
    def default_mic(self) -> str | None:
        return self._values.get("default_mic")

    @default_mic.setter
    def default_mic(self, name: str | None) -> None:
        self.set("default_mic", name)

    @property
    def whisper_model(self) -> str:
        return str(self._values.get("whisper_model", "base"))

    @whisper_model.setter
    def whisper_model(self, model: str) -> None:
        self.set("whisper_model", model)

    @property
    def dictation_model(self) -> str:
        return str(self._values.get("dictation_model", "base"))

    @dictation_model.setter
    def dictation_model(self, model: str) -> None:
        self.set("dictation_model", model)

    @property
    def dictation_hotkey(self) -> str:
        return str(self._values.get("dictation_hotkey", "left_ctrl"))

    @dictation_hotkey.setter
    def dictation_hotkey(self, key: str) -> None:
        self.set("dictation_hotkey", key)

    @property
    def dictation_auto_enter(self) -> bool:
        return bool(self._values.get("dictation_auto_enter", True))

    @dictation_auto_enter.setter
    def dictation_auto_enter(self, value: bool) -> None:
        self.set("dictation_auto_enter", value)

    @property
    def open_transcript_app(self) -> str:
        return str(self._values.get("open_transcript_app", "default"))

    @open_transcript_app.setter
    def open_transcript_app(self, app: str) -> None:
        self.set("open_transcript_app", app)

    def open_transcript(self, file_path: str) -> None:
        """Open the transcript file with the app set in Settings (macOS open/open -a)."""
        app_name = self.open_transcript_app
        if not app_name or app_name == "default":
            subprocess.run(["open", file_path], check=False)
            return
        subprocess.run(["open", "-a", app_name, file_path], check=False)
        logger.debug("Opened %s with %s", file_path, app_name)

    @property
    def launch_hotkey(self) -> str | None:
        return self._values.get("launch_hotkey")

    @launch_hotkey.setter
    def launch_hotkey(self, combo: str | None) -> None:
        self.set("launch_hotkey", combo)

    @property
    def auto_clipboard(self) -> bool:
        return bool(self._values.get("auto_clipboard", True))

    @auto_clipboard.setter
    def auto_clipboard(self, value: bool) -> None:
        self.set("auto_clipboard", value)

    @property
    def sample_rate(self) -> int:
        return int(self._values.get("sample_rate", 16000))

    @sample_rate.setter
    def sample_rate(self, rate: int) -> None:
        self.set("sample_rate", rate)

    @property
    def channels(self) -> int:
        return int(self._values.get("channels", 1))

    @channels.setter
    def channels(self, count: int) -> None:
        self.set("channels", count)

    @property
    def speaker_device(self) -> str:
        return str(self._values.get("speaker_device", "Multi-Output Device"))

    @speaker_device.setter
    def speaker_device(self, name: str) -> None:
        self.set("speaker_device", name)

    @property
    def blackhole_device(self) -> str:
        return str(self._values.get("blackhole_device", "BlackHole 2ch"))

    @blackhole_device.setter
    def blackhole_device(self, name: str) -> None:
        self.set("blackhole_device", name)

    @property
    def language(self) -> str:
        return str(self._values.get("language", "en"))

    @language.setter
    def language(self, lang: str) -> None:
        self.set("language", lang)

    @property
    def group_consecutive_speaker_lines(self) -> bool:
        return bool(self._values.get("group_consecutive_speaker_lines", True))

    @group_consecutive_speaker_lines.setter
    def group_consecutive_speaker_lines(self, value: bool) -> None:
        self.set("group_consecutive_speaker_lines", value)

    @property
    def source_include_timestamps(self) -> bool:
        return bool(self._values.get("source_include_timestamps", False))

    @source_include_timestamps.setter
    def source_include_timestamps(self, value: bool) -> None:
        self.set("source_include_timestamps", value)

    @property
    def suppress_mic_bleed_duplicates(self) -> bool:
        return bool(self._values.get("suppress_mic_bleed_duplicates", True))

    @suppress_mic_bleed_duplicates.setter
    def suppress_mic_bleed_duplicates(self, value: bool) -> None:
        self.set("suppress_mic_bleed_duplicates", value)

    @property
    def mic_bleed_similarity_threshold(self) -> float:
        return float(self._values.get("mic_bleed_similarity_threshold", 0.62))

    @mic_bleed_similarity_threshold.setter
    def mic_bleed_similarity_threshold(self, value: float) -> None:
        self.set("mic_bleed_similarity_threshold", value)

    @property
    def command_alias(self) -> str:
        return str(self._values.get("command_alias", "rec"))

    @command_alias.setter
    def command_alias(self, alias: str) -> None:
        self.set("command_alias", alias)

    @property
    def record_here_by_default(self) -> bool:
        return bool(self._values.get("record_here_by_default", False))

    @record_here_by_default.setter
    def record_here_by_default(self, value: bool) -> None:
        self.set("record_here_by_default", value)

    @property
    def dictation_sounds(self) -> bool:
        return bool(self._values.get("dictation_sounds", True))

    @dictation_sounds.setter
    def dictation_sounds(self, value: bool) -> None:
        self.set("dictation_sounds", value)

    @property
    def rec_binary_path(self) -> str | None:
        return self._values.get("rec_binary_path")

    @rec_binary_path.setter
    def rec_binary_path(self, path: str | None) -> None:
        self.set("rec_binary_path", path)

    # ------------------------------------------------------------------
    # Scribe-specific settings (Phase 4)
    # ------------------------------------------------------------------

    @property
    def keep_wav(self) -> bool:
        """Whether to retain the WAV file after successful transcription."""
        return bool(self._values.get("keep_wav", False))

    @keep_wav.setter
    def keep_wav(self, value: bool) -> None:
        self.set("keep_wav", value)

    @property
    def scribe_models(self) -> list[str]:
        """Model names selected by default for Scribe sessions."""
        raw = self._values.get("scribe_models", ["base"])
        if isinstance(raw, list):
            return list(raw)
        return [str(raw)]

    @scribe_models.setter
    def scribe_models(self, models: list[str]) -> None:
        self.set("scribe_models", list(models))
