"""Onboarding panel bridge.

Translates JS calls from onboarding.html into controller and permission calls.
App callbacks for open_scribe, open_transcribe_with_sample, on_onboarding_complete,
on_open_settings_general.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any, Callable

from liscribe.services import permissions_service as _perms

if TYPE_CHECKING:
    from liscribe.controllers.onboarding_controller import OnboardingController

logger = logging.getLogger(__name__)

APP_PICKER_FILE_TYPES = ("Applications (*.app)",)


class OnboardingBridge:
    """JS-callable API for the onboarding panel.

    Receives controller and callbacks from app. download_model runs in a
    background thread; get_download_progress returns bridge-held state.
    """

    def __init__(
        self,
        controller: OnboardingController,
        on_open_scribe: Callable[[], None],
        on_open_transcribe_with_sample: Callable[[], None],
        on_onboarding_complete: Callable[[], None],
        on_open_help: Callable[[str], None] | None = None,
        on_open_settings_general: Callable[[], None] | None = None,
        on_relaunch: Callable[[], None] | None = None,
    ) -> None:
        self._controller = controller
        self._on_open_scribe = on_open_scribe
        self._on_open_transcribe_with_sample = on_open_transcribe_with_sample
        self._on_onboarding_complete = on_onboarding_complete
        self._on_open_help = on_open_help
        self._on_open_settings_general = on_open_settings_general
        self._on_relaunch = on_relaunch
        self._window: Any = None
        self._download_state: dict[str, Any] = {}
        self._download_lock = threading.Lock()

    def set_window(self, window: Any) -> None:
        """Set the pywebview window so dialogs (e.g. app picker) are parented to it."""
        self._window = window

    def get_step(self) -> dict[str, Any]:
        """Return current step payload from controller."""
        return self._controller.get_step()

    def advance(self) -> dict[str, Any]:
        """Validate and move to next step. On done, call on_onboarding_complete."""
        result = self._controller.advance()
        if result.get("ok") and self._controller.get_step().get("step_id") == "done":
            if self._on_onboarding_complete:
                self._on_onboarding_complete()
        return result

    def back(self) -> dict[str, Any]:
        """Move to previous step."""
        return self._controller.back()

    def request_permission(self, permission_type: str) -> None:
        """Open System Settings pane for the given permission (microphone, accessibility, input_monitoring)."""
        _perms.open_system_settings(permission_type)

    def check_permission(self, permission_type: str) -> bool:
        """Return whether the given permission is granted."""
        perms = _perms.get_all_permissions()
        return bool(perms.get(permission_type, False))

    def download_model(self, name: str) -> dict[str, Any]:
        """Start downloading a model in a background thread. Returns immediately."""
        with self._download_lock:
            if self._download_state.get("model") and not self._download_state.get("done"):
                return {"started": False, "error": "Another download in progress"}

        def run() -> None:
            with self._download_lock:
                self._download_state = {"model": name, "progress": 0.0, "done": False}
            try:
                self._controller._model.download(name, on_progress=lambda p: _set_progress(name, p))
                with self._download_lock:
                    self._download_state = {"model": name, "progress": 1.0, "done": True}
            except Exception as exc:
                logger.warning("onboarding download_model %s failed: %s", name, exc)
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
        """Return current download state for the UI."""
        with self._download_lock:
            return dict(self._download_state)

    def is_complete(self) -> bool:
        """Return whether onboarding has been completed (persisted)."""
        return self._controller.is_complete()

    def get_sample_audio_path(self) -> str:
        """Return path to bundled sample WAV for Practice Transcribe step."""
        return str(self._controller.get_sample_audio_path())

    def open_scribe(self) -> None:
        """Open Scribe panel (practice step). Called from UI."""
        if self._on_open_scribe:
            self._on_open_scribe()

    def open_transcribe_with_sample(self) -> None:
        """Open Transcribe panel with sample audio pre-filled. Called from UI."""
        if self._on_open_transcribe_with_sample:
            self._on_open_transcribe_with_sample()

    def open_help(self, anchor: str) -> None:
        """Open Settings to the Help tab at the given anchor (e.g. blackhole). Called from UI."""
        if self._on_open_help:
            self._on_open_help(anchor or "permissions")

    def check_blackhole(self) -> dict[str, Any]:
        """Return BlackHole install status for the onboarding step (same as Settings → Deps)."""
        from liscribe import platform_setup
        ok, msg = platform_setup.check_blackhole()
        return {"installed": ok, "message": msg}

    def get_dictation_auto_enter(self) -> bool:
        """Return the dictation auto-enter setting (same as Settings → General)."""
        return self._controller.get_dictation_auto_enter()

    def set_dictation_auto_enter(self, value: bool) -> None:
        """Set the dictation auto-enter setting (persisted in config)."""
        self._controller.set_dictation_auto_enter(value)

    def get_open_transcript_app(self) -> str:
        """Return the app name used to open transcripts (display name for UI)."""
        return self._controller.get_open_transcript_app()

    def set_open_transcript_app(self, name: str) -> None:
        """Set the app name for opening transcripts (persisted in config)."""
        self._controller.set_open_transcript_app(name)

    def pick_app(self) -> dict[str, str] | None:
        """Open native file picker for /Applications; return {name, path} or None if cancelled."""
        import webview
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
            name = path.split("/")[-1].replace(".app", "")
            self._controller.set_open_transcript_app(name)
            return {"name": name, "path": path}
        except Exception as exc:
            logger.warning("pick_app failed: %s", exc)
            return None

    def open_settings_general(self) -> None:
        """Close onboarding and open Settings with the General tab selected."""
        if self._on_open_settings_general:
            self._on_open_settings_general()

    def relaunch_app(self) -> None:
        """Relaunch the app so newly-granted permissions take effect."""
        if self._on_relaunch:
            self._on_relaunch()
