"""Settings panel bridge.

Translates JS calls from settings.html into config/model/permissions calls.
No business logic — translation layer only.

pywebview exposes every public method as a JS-callable function on
window.pywebview.api.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any, Callable

import webview

from liscribe.services import permissions_service as _perms
from liscribe.services.config_service import ConfigService

if TYPE_CHECKING:
    from liscribe.services.audio_service import AudioService
    from liscribe.services.model_service import ModelService

logger = logging.getLogger(__name__)

# App picker file type for native dialog
APP_PICKER_FILE_TYPES = ("Applications (*.app)",)


def _get_version() -> str:
    try:
        from importlib.metadata import version
        return version("liscribe")
    except Exception:
        return "0.2.0"


class SettingsBridge:
    """JS-callable API for the Settings panel.

    Receives config and model services as constructor arguments.
    set_window() is called after the panel is created for pick_app() and
    navigate_help().
    """

    def __init__(
        self,
        config: ConfigService,
        model: ModelService,
        audio: AudioService,
        on_close: Callable[[], None] | None = None,
        on_restart: Callable[[], None] | None = None,
        on_launch_hotkey_changed: Callable[[], None] | None = None,  # Reserved for future in-process listener restart; not called (hotkeys apply after full app restart).
        on_dictation_hotkey_changed: Callable[[], None] | None = None,  # Same as above.
        on_replay_setup_guide: Callable[[], None] | None = None,
    ) -> None:
        self._config = config
        self._model = model
        self._audio = audio
        self._on_close = on_close
        self._on_restart = on_restart
        self._on_launch_hotkey_changed = on_launch_hotkey_changed
        self._on_dictation_hotkey_changed = on_dictation_hotkey_changed
        self._on_replay_setup_guide = on_replay_setup_guide
        self._window: Any = None
        self._download_state: dict[str, Any] = {}
        self._download_lock = threading.Lock()

    def close_window(self) -> None:
        """Close the Settings panel. Called when user clicks the header close button."""
        if self._on_close is not None:
            self._on_close()

    def restart_app(self) -> None:
        """Close the app and relaunch it after a short delay. Used to apply new hotkeys."""
        if self._on_restart is not None:
            self._on_restart()

    def replay_setup_guide(self) -> None:
        """Open the onboarding wizard from step 1 (Settings → Help → Replay setup guide)."""
        if self._on_replay_setup_guide is not None:
            self._on_replay_setup_guide()

    def set_window(self, window: Any) -> None:
        """Set the pywebview window for pick_app and navigate_help. Called by app after create_window."""
        self._window = window

    # ------------------------------------------------------------------
    # Config / devices
    # ------------------------------------------------------------------

    def get_mics(self) -> list[dict[str, Any]]:
        """Return available microphones for the default mic dropdown."""
        try:
            return self._audio.list_mics()
        except Exception as exc:
            logger.warning("get_mics failed: %s", exc)
            return []

    def get_config(self) -> dict[str, Any]:
        """Return all config values needed by the Settings UI."""
        return {
            "save_folder": self._config.save_folder,
            "default_mic": self._config.default_mic,
            "keep_wav": self._config.keep_wav,
            "dictation_auto_enter": self._config.dictation_auto_enter,
            "start_on_login": self._config.start_on_login,
            "open_transcript_app": self._config.open_transcript_app,
            "launch_hotkey": self._config.launch_hotkey,
            "dictation_hotkey": self._config.dictation_hotkey,
            "scribe_models": list(self._config.scribe_models),
            "dictation_model": self._config.dictation_model,
            "speaker_device": self._config.speaker_device,
            "blackhole_device": self._config.blackhole_device,
        }

    def set_config(self, key: str, value: Any) -> None:
        """Persist a single config key. start_on_login and scribe_models are not in config.json; handled here."""
        if key == "start_on_login":
            self._config.start_on_login = bool(value)
            return
        if key == "scribe_models":
            self._config.scribe_models = value if isinstance(value, list) else list(value)
            return
        self._config.set(key, value)
        # Hotkey changes are saved only; new shortcuts apply after app restart (in-process listener restart crashes on macOS).

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------

    def list_models(self) -> list[dict[str, Any]]:
        """Return all models with download status and size."""
        return self._model.list_models()

    def download_model(self, name: str) -> dict[str, Any]:
        """Start downloading a model in a background thread. Returns immediately."""
        with self._download_lock:
            if self._download_state.get("model") and not self._download_state.get("done"):
                return {"started": False, "error": "Another download in progress"}

        def run() -> None:
            with self._download_lock:
                self._download_state = {"model": name, "progress": 0.0, "done": False}
            try:
                self._model.download(name, on_progress=lambda p: _set_progress(name, p))

                with self._download_lock:
                    self._download_state = {"model": name, "progress": 1.0, "done": True}
            except Exception as exc:
                logger.warning("download_model %s failed: %s", name, exc)
                with self._download_lock:
                    self._download_state = {
                        "model": name,
                        "progress": 0.0,
                        "done": True,
                        "error": str(exc),
                    }

        def _set_progress(m: str, p: float) -> None:
            with self._download_lock:
                if self._download_state.get("model") == m:
                    self._download_state["progress"] = p

        t = threading.Thread(target=run, daemon=True)
        t.start()
        return {"started": True}

    def get_download_progress(self) -> dict[str, Any]:
        """Return current download state for the UI (progress, done, error)."""
        with self._download_lock:
            return dict(self._download_state)

    def remove_model(self, name: str) -> dict[str, Any]:
        """Remove a downloaded model. Returns {ok} or {ok: False, reason, message}."""
        scribe_defaults = set(self._config.scribe_models)
        dictate_default = self._config.dictation_model
        if name in scribe_defaults:
            return {
                "ok": False,
                "reason": "default_scribe",
                "message": "This model is a Scribe default. Choose a replacement in Scribe default models first.",
            }
        if name == dictate_default:
            return {
                "ok": False,
                "reason": "default_dictate",
                "message": "This model is the Dictate model. Choose another Dictate model first.",
            }
        success, message = self._model.remove(name)
        return {"ok": success, "message": message} if not success else {"ok": True}

    # ------------------------------------------------------------------
    # Permissions
    # ------------------------------------------------------------------

    def get_permissions(self) -> dict[str, bool]:
        """Return live permission status (microphone, accessibility, input_monitoring)."""
        return _perms.get_all_permissions()

    def open_system_settings(self, pane: str) -> None:
        """Open the given System Settings pane (microphone, accessibility, input_monitoring)."""
        _perms.open_system_settings(pane)

    def get_python_paths(self) -> dict[str, str]:
        """Return Python binary paths for Input Monitoring setup guidance."""
        return _perms.get_python_executable_paths()

    # ------------------------------------------------------------------
    # App picker / Help
    # ------------------------------------------------------------------

    def pick_folder(self) -> str | None:
        """Open native folder picker. Returns path or None if cancelled."""
        if self._window is None:
            return None
        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.FOLDER,
                allow_multiple=False,
            )
            if result and len(result) > 0:
                return result[0]
            return None
        except Exception as exc:
            logger.warning("pick_folder failed: %s", exc)
            return None

    def pick_app(self) -> dict[str, str] | None:
        """Open native folder/file picker for /Applications; return {name, path} or None if cancelled."""
        if self._window is None:
            return None
        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=APP_PICKER_FILE_TYPES,
                directory="/Applications",
            )
            if not result or len(result) == 0:
                return None
            path = result[0]
            if not path.endswith(".app"):
                return None
            # Name for "open -a Name file": use bundle name without .app
            name = path.split("/")[-1].replace(".app", "")
            return {"name": name, "path": path}
        except Exception as exc:
            logger.warning("pick_app failed: %s", exc)
            return None

    def open_help(self, anchor: str) -> None:
        """Navigate the Help tab to the named section. Called from JS or from app (e.g. Setup Required)."""
        if self._window is None:
            return
        try:
            self._window.evaluate_js(
                f"window.__liscribeNavigateHelp && window.__liscribeNavigateHelp({repr(anchor)});"
            )
        except Exception as exc:
            logger.debug("open_help evaluate_js: %s", exc)

    def get_app_version(self) -> str:
        """Return the app version string."""
        return _get_version()

    # ------------------------------------------------------------------
    # Dependencies (BlackHole)
    # ------------------------------------------------------------------

    def check_blackhole(self) -> dict[str, Any]:
        """Return BlackHole install status for Deps tab."""
        from liscribe import platform_setup
        ok, msg = platform_setup.check_blackhole()
        return {"installed": ok, "message": msg}

    def check_multi_output_device(self, device_name: str) -> dict[str, Any]:
        """Return multi-output device status for Deps tab. device_name must match Audio MIDI Setup."""
        from liscribe import platform_setup
        ok, msg = platform_setup.check_multi_output_device(device_name)
        return {"installed": ok, "message": msg}

    # ------------------------------------------------------------------
    # Replacements (Phase 10)
    # ------------------------------------------------------------------

    def _rule_is_default(self, rule: dict[str, Any]) -> bool:
        """True if rule matches one of the built-in default rules."""
        for default in ConfigService.DEFAULT_REPLACEMENT_RULES:
            if (
                rule.get("trigger") == default.get("trigger")
                and rule.get("type") == default.get("type")
                and rule.get("scope") == default.get("scope")
            ):
                if default.get("type") == "wrap":
                    if rule.get("prefix") == default.get("prefix") and rule.get("suffix") == default.get("suffix"):
                        return True
                else:
                    if rule.get("output") == default.get("output"):
                        return True
        return False

    def get_replacements(self) -> list[dict[str, Any]]:
        """Return all replacement rules, each with is_default set."""
        rules = [dict(r) for r in self._config.replacement_rules]
        for r in rules:
            r["is_default"] = self._rule_is_default(r)
        return rules

    def add_replacement(
        self,
        trigger: str,
        type: str,  # noqa: A002
        output: str = "",
        prefix: str = "",
        suffix: str = "",
        scope: str = "both",
    ) -> dict[str, Any]:
        """Add a replacement rule. Returns {ok: True, rule} or {ok: False, error}."""
        trigger = (trigger or "").strip()
        if not trigger:
            return {"ok": False, "error": "Trigger cannot be empty"}
        if type in ("simple", "newline") and not (output or "").strip():
            return {"ok": False, "error": "Output cannot be empty for this type"}
        rule: dict[str, Any] = {
            "trigger": trigger,
            "type": type,
            "output": (output or "").strip(),
            "scope": scope or "both",
        }
        if type == "wrap":
            rule["prefix"] = prefix or ""
            rule["suffix"] = suffix or ""
        rules = self._config.replacement_rules
        rules = list(rules)
        rules.append(rule)
        self._config.replacement_rules = rules
        rule["is_default"] = self._rule_is_default(rule)
        return {"ok": True, "rule": rule}

    def update_replacement(
        self,
        index: int,
        trigger: str,
        type: str,  # noqa: A002
        output: str = "",
        prefix: str = "",
        suffix: str = "",
        scope: str = "both",
    ) -> dict[str, Any]:
        """Update rule at index. Returns {ok: True, rule} or {ok: False, error}."""
        trigger = (trigger or "").strip()
        if not trigger:
            return {"ok": False, "error": "Trigger cannot be empty"}
        if type in ("simple", "newline") and not (output or "").strip():
            return {"ok": False, "error": "Output cannot be empty for this type"}
        rules = list(self._config.replacement_rules)
        if index < 0 or index >= len(rules):
            return {"ok": False, "error": "Invalid index"}
        rule = {
            "trigger": trigger,
            "type": type,
            "output": (output or "").strip(),
            "scope": scope or "both",
        }
        if type == "wrap":
            rule["prefix"] = prefix or ""
            rule["suffix"] = suffix or ""
        rules[index] = rule
        self._config.replacement_rules = rules
        rule["is_default"] = self._rule_is_default(rule)
        return {"ok": True, "rule": rule}

    def delete_replacement(self, index: int) -> dict[str, Any]:
        """Delete rule at index. Returns {ok: True} or {ok: False, error}."""
        rules = list(self._config.replacement_rules)
        if index < 0 or index >= len(rules):
            return {"ok": False, "error": "Invalid index"}
        rules.pop(index)
        self._config.replacement_rules = rules
        return {"ok": True}

    # ------------------------------------------------------------------
    # Crash recovery (Phase 6)
    # ------------------------------------------------------------------

    def get_crash_recovery_enabled(self) -> bool:
        """Return True if the crash recovery LaunchAgent plist is installed."""
        from liscribe.services.config_service import is_crash_recovery_enabled
        return is_crash_recovery_enabled()

    def set_crash_recovery_enabled(self, enabled: bool) -> dict[str, Any]:
        """Install or uninstall the crash recovery LaunchAgent."""
        from liscribe.services.config_service import (
            _get_app_bundle_path,
            install_crash_recovery_agent,
            uninstall_crash_recovery_agent,
        )
        try:
            if enabled:
                bundle = _get_app_bundle_path()
                if bundle is None:
                    return {"ok": False, "error": "Not running as .app bundle; crash recovery not available."}
                install_crash_recovery_agent(bundle)
            else:
                uninstall_crash_recovery_agent()
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
