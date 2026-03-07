"""Dictate panel bridge — JS-to-Python call translation.

Exposes three polling methods called by the Dictate panel HTML:
  get_waveform(bars)  — for the live waveform display
  get_elapsed()       — for the elapsed timer
  get_state()         — 'recording' | 'processing' | 'idle' for view switching

No business logic here. All calls delegate to DictateController.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from liscribe.controllers.dictate_controller import DictateController

logger = logging.getLogger(__name__)


class DictateBridge:
    """pywebview JS API for the Dictate panel.

    Passed as js_api when the panel window is created. pywebview injects
    it as window.pywebview.api in the panel HTML.
    """

    def __init__(self, controller: "DictateController") -> None:
        self._controller = controller

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
