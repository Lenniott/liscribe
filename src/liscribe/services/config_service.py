"""Singleton wrapper around config.py that provides typed get/set access."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

from liscribe import config as _config

logger = logging.getLogger(__name__)

# UI-only prefs not in config.py (engine frozen). Persisted in CONFIG_DIR.
UI_PREFS_PATH = Path(_config.CONFIG_DIR) / "ui_prefs.json"
START_ON_LOGIN_KEY = "start_on_login"


_LAUNCHD_PLIST = Path.home() / "Library/LaunchAgents/com.liscribe.app.plist"


def _get_app_bundle_path() -> Path | None:
    """If we are running inside a .app bundle, return its path; else None."""
    exe = Path(sys.executable).resolve()
    # Walk up at most 3 levels: exe -> MacOS -> Contents -> .app
    for _ in range(3):
        if exe.suffix == ".app" or (exe.parent.name == "MacOS" and exe.parent.parent.name == "Contents"):
            if exe.parent.name == "MacOS":
                return exe.parent.parent.parent
            return exe
        exe = exe.parent
    return None


def _set_login_item(enabled: bool) -> None:
    """Enable or disable Start on Login via the launchd plist written by install.sh."""
    if not _LAUNCHD_PLIST.exists():
        logger.info("No launchd plist found; Start on Login has no effect until install.sh is run")
        return
    cmd = [
        "/usr/libexec/PlistBuddy",
        "-c",
        f"Set :RunAtLoad {'true' if enabled else 'false'}",
        str(_LAUNCHD_PLIST),
    ]
    subprocess.run(cmd, check=False, capture_output=True)
    subprocess.run(["launchctl", "unload", str(_LAUNCHD_PLIST)], check=False, capture_output=True)
    if enabled:
        subprocess.run(["launchctl", "load", str(_LAUNCHD_PLIST)], check=False, capture_output=True)


def _get_login_item_from_plist() -> bool:
    """Read RunAtLoad from the launchd plist; returns False if plist missing or unreadable."""
    if not _LAUNCHD_PLIST.exists():
        return False
    try:
        import plistlib
        data = plistlib.loads(_LAUNCHD_PLIST.read_bytes())
        return bool(data.get("RunAtLoad", False))
    except Exception:
        logger.debug("Could not read RunAtLoad from launchd plist", exc_info=True)
        return False


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
    def dictation_hotkey_display(self) -> str:
        """Short symbol for the configured dictation hotkey, e.g. '^' for ctrl."""
        _display = {
            "left_ctrl": "^",
            "right_ctrl": "^",
            "right_option": "⌥",
            "right_shift": "⇧",
            "caps_lock": "⇪",
        }
        return _display.get(self.dictation_hotkey, "^")

    @property
    def dictation_auto_enter(self) -> bool:
        v = self._values.get("dictation_auto_enter", True)
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.lower() in ("false", "0", "no"):
            return False
        return bool(v)

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

    @property
    def webhook_url(self) -> str | None:
        v = self._values.get("webhook_url")
        return str(v) if v else None

    @webhook_url.setter
    def webhook_url(self, url: str | None) -> None:
        self.set("webhook_url", url or None)

    @property
    def webhook_auth_header_name(self) -> str:
        return str(self._values.get("webhook_auth_header_name") or "")

    @webhook_auth_header_name.setter
    def webhook_auth_header_name(self, name: str) -> None:
        self.set("webhook_auth_header_name", name or "")

    @property
    def webhook_auth_header_value(self) -> str:
        return str(self._values.get("webhook_auth_header_value") or "")

    @webhook_auth_header_value.setter
    def webhook_auth_header_value(self, value: str) -> None:
        self.set("webhook_auth_header_value", value or "")

    @property
    def webhook_auto_send_transcripts(self) -> bool:
        return bool(self._values.get("webhook_auto_send_transcripts", False))

    @webhook_auto_send_transcripts.setter
    def webhook_auto_send_transcripts(self, value: bool) -> None:
        self.set("webhook_auto_send_transcripts", value)

    @property
    def webhook_auto_send_dictate(self) -> bool:
        return bool(self._values.get("webhook_auto_send_dictate", False))

    @webhook_auto_send_dictate.setter
    def webhook_auto_send_dictate(self, value: bool) -> None:
        self.set("webhook_auto_send_dictate", value)

    @property
    def mic_label(self) -> str:
        return str(self._values.get("mic_label") or "in")

    @mic_label.setter
    def mic_label(self, label: str) -> None:
        self.set("mic_label", label or "in")

    @property
    def speaker_label(self) -> str:
        return str(self._values.get("speaker_label") or "out")

    @speaker_label.setter
    def speaker_label(self, label: str) -> None:
        self.set("speaker_label", label or "out")

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

    # ------------------------------------------------------------------
    # Word replacement rules (Phase 10)
    # ------------------------------------------------------------------

    CONFIG_KEY_REPLACEMENT_RULES = "replacement_rules"

    DEFAULT_REPLACEMENT_RULES: list[dict[str, Any]] = [
        # hashtag Monday -> #monday
        {"trigger": "hashtag", "type": "wrap", "prefix": "#", "suffix": "", "scope": "both", "transform": "lower"},
        # "to do" -> [ ]
        {"trigger": "to do", "type": "simple", "output": "[ ]", "scope": "both"},
        {"trigger": "open bracket", "type": "simple", "output": "[", "scope": "both"},
        {"trigger": "close bracket", "type": "simple", "output": "]", "scope": "both"},
        {"trigger": "dash", "type": "simple", "output": "-", "scope": "both"},
        # "new line" -> newline
        {"trigger": "new line", "type": "newline", "output": "\n", "scope": "both"},
    ]

    @property
    def replacement_rules(self) -> list[dict[str, Any]]:
        """Replacement rules for word substitution. Seeds defaults if key absent."""
        key = self.CONFIG_KEY_REPLACEMENT_RULES
        if key not in self._values:
            self._values[key] = [dict(r) for r in self.DEFAULT_REPLACEMENT_RULES]
            _config.save_config(self._values)
        raw = self._values[key]
        if not isinstance(raw, list):
            return [dict(r) for r in self.DEFAULT_REPLACEMENT_RULES]
        return [dict(r) for r in raw]

    @replacement_rules.setter
    def replacement_rules(self, rules: list[dict[str, Any]]) -> None:
        self.set(self.CONFIG_KEY_REPLACEMENT_RULES, list(rules))

    # ------------------------------------------------------------------
    # Onboarding (Phase 8 — first-launch wizard completion)
    # ------------------------------------------------------------------

    @property
    def onboarding_complete(self) -> bool:
        """Whether the first-launch onboarding wizard has been completed."""
        return bool(self._values.get("onboarding_complete", False))

    @onboarding_complete.setter
    def onboarding_complete(self, value: bool) -> None:
        self.set("onboarding_complete", value)

    # ------------------------------------------------------------------
    # Start on Login (Phase 7 — persisted in ui_prefs.json, not config.py)
    # ------------------------------------------------------------------

    @property
    def start_on_login(self) -> bool:
        """Whether to start Liscribe on user login.
        Primary source: RunAtLoad in the launchd plist (written by install.sh).
        Falls back to ui_prefs.json for backwards compatibility.
        """
        # Prefer the ground truth in the plist when it exists.
        if _LAUNCHD_PLIST.exists():
            return _get_login_item_from_plist()
        try:
            if UI_PREFS_PATH.exists():
                data = json.loads(UI_PREFS_PATH.read_text(encoding="utf-8"))
                return bool(data.get(START_ON_LOGIN_KEY, False))
        except Exception:
            logger.debug("Could not read ui_prefs.json", exc_info=True)
        return False

    @start_on_login.setter
    def start_on_login(self, value: bool) -> None:
        _config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        if UI_PREFS_PATH.exists():
            try:
                data = json.loads(UI_PREFS_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        data[START_ON_LOGIN_KEY] = value
        UI_PREFS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Saved start_on_login=%s to %s", value, UI_PREFS_PATH)
        _set_login_item(value)
