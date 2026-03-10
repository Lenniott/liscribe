"""Dictate panel bridge — JS-to-Python call translation.

Exposes three polling methods called by the Dictate panel HTML:
  get_waveform(bars)  — for the live waveform display
  get_elapsed()       — for the elapsed timer
  get_state()         — 'recording' | 'processing' | 'idle' for view switching

No business logic here. All calls delegate to DictateController.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from liscribe.controllers.dictate_controller import DictateController

logger = logging.getLogger(__name__)


class DictateBridge:
    """pywebview JS API for the Dictate panel.

    Passed as js_api when the panel window is created. pywebview injects
    it as window.pywebview.api in the panel HTML.
    """

    def __init__(
        self,
        controller: "DictateController",
        on_open_settings_help: Callable[[str], None] | None = None,
    ) -> None:
        self._controller = controller
        self._on_open_settings_help = on_open_settings_help or (lambda _: None)
        self._on_close_dialog: Callable[[], None] | None = None

    def set_close_dialog(self, fn: Callable[[], None]) -> None:
        """Register a callback that closes the Setup Required dialog. Called by app.py."""
        self._on_close_dialog = fn

    def open_system_prefs(self, pane: str) -> None:
        """Open System Preferences to the given pane (e.g. Privacy_Accessibility). Called from Setup Required modal."""
        try:
            import subprocess
            subprocess.Popen(["open", f"x-apple.systempreferences:{pane}"])
        except Exception:
            logger.debug("DictateBridge.open_system_prefs failed", exc_info=True)

    def close_dialog(self) -> None:
        """Close the Setup Required dialog. Called from 'Not now' button."""
        if self._on_close_dialog:
            try:
                self._on_close_dialog()
            except Exception:
                logger.debug("DictateBridge.close_dialog failed", exc_info=True)

    def open_settings_help(self, anchor: str) -> None:
        """Open Settings panel to the given Help section (e.g. permissions). Used by Setup Required modal."""
        self._on_open_settings_help(anchor)

    def get_waveform(self, bars: int = 30) -> list[float]:
        """Return audio level bars (0.0–1.0) for waveform rendering.

        Returns an empty list on any error so the panel degrades gracefully.
        """
        try:
            return self._controller.get_waveform(bars=bars)
        except Exception:
            logger.debug("DictateBridge.get_waveform failed", exc_info=True)
            return []

    def get_elapsed(self) -> float:
        """Return seconds elapsed since recording started, or 0.0.

        Returns 0.0 on any error.
        """
        try:
            return self._controller.get_elapsed()
        except Exception:
            logger.debug("DictateBridge.get_elapsed failed", exc_info=True)
            return 0.0

    def get_state(self) -> str:
        """Return 'recording' | 'processing' | 'idle' for panel view switching."""
        try:
            return self._controller.get_ui_state()
        except Exception:
            logger.debug("DictateBridge.get_state failed", exc_info=True)
            return "idle"

    def stop_recording(self) -> dict:
        """Stop recording via UI button — clipboard copy only, no paste.

        Reserved for future HTML panel — not currently invoked from JS
        (native overlay uses callback via doneAction_ / _on_dictate_done).
        """
        try:
            return self._controller.request_stop_from_button()
        except Exception:
            logger.debug("DictateBridge.stop_recording failed", exc_info=True)
            return {"ok": False}
