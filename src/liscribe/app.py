"""Liscribe v2 — menu bar application entry point.

Integration notes:
  Both rumps and pywebview use NSApplication.sharedApplication().
  Importing webview.platforms.cocoa sets BrowserView.app to that shared
  instance. rumps.App.run() then starts the NSApplication event loop via
  AppHelper.runEventLoop(). When a panel is opened, guilib.create_window()
  checks BrowserView.app.isRunning() and, finding it True, skips starting
  a second event loop — it just creates a WKWebView window within the
  already-running loop.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import rumps
import webview

from liscribe.bridge.scribe_bridge import ScribeBridge
from liscribe.controllers.scribe_controller import ScribeController
from liscribe.services.audio_service import AudioService
from liscribe.services.config_service import ConfigService
from liscribe.services.hotkey_service import HotkeyService
from liscribe.services.model_service import ModelService

logger = logging.getLogger(__name__)

PANELS_DIR = Path(__file__).parent / "ui" / "panels"

if sys.platform != "darwin":
    raise RuntimeError("Liscribe requires macOS.")

# Wire webview's guilib without calling webview.start().
# cocoa.py imports NSApplication.sharedApplication() at class-definition
# time, so guilib is usable as soon as the module is imported.
import webview.platforms.cocoa as _cocoa_guilib  # noqa: E402

webview.guilib = _cocoa_guilib
webview.renderer = _cocoa_guilib.renderer


class LiscribleApp(rumps.App):
    """Menu bar application.

    Owns the four singleton services and manages the lifecycle of
    pywebview panel windows.
    """

    def __init__(
        self,
        config: ConfigService,
        audio: AudioService,
        model: ModelService,
        hotkey: HotkeyService,
    ) -> None:
        super().__init__("🎙", quit_button="Quit")

        self._config = config
        self._audio = audio
        self._model = model
        self._hotkey = hotkey

        # Scribe controller + bridge — one instance for the app lifetime.
        # The controller is reset between sessions; the bridge is stateless.
        self._scribe_ctrl = ScribeController(
            audio=audio, model=model, config=config
        )
        self._scribe_bridge = ScribeBridge(
            controller=self._scribe_ctrl, model=model, audio=audio
        )

        # name → open webview.Window (None-entry means window was closed)
        self._panels: dict[str, webview.Window] = {}

        self.menu = [
            rumps.MenuItem("Scribe  ⌃⌥L", callback=self.open_scribe),
            rumps.MenuItem("Dictate  ⌃⌃ / hold ⌃", callback=self.open_dictate),
            rumps.MenuItem("Transcribe", callback=self.open_transcribe),
            rumps.MenuItem("Settings", callback=self.open_settings),
        ]

    # ------------------------------------------------------------------
    # Panel management
    # ------------------------------------------------------------------

    def _panel_url(self, name: str) -> str:
        return (PANELS_DIR / f"{name}.html").as_uri()

    def _open_panel(
        self,
        name: str,
        title: str,
        width: int = 560,
        height: int = 620,
        resizable: bool = True,
        js_api: object | None = None,
    ) -> None:
        """Open a named panel, raising it if already open."""
        existing = self._panels.get(name)
        if existing is not None:
            try:
                existing.show()
                return
            except Exception:
                logger.warning("Could not show existing panel %r; recreating", name, exc_info=True)
                self._panels.pop(name, None)

        window = webview.create_window(
            title,
            self._panel_url(name),
            width=width,
            height=height,
            resizable=resizable,
            min_size=(400, 300),
            **({} if js_api is None else {"js_api": js_api}),
        )

        def _on_closed() -> None:
            self._panels.pop(name, None)

        window.events.closed += _on_closed
        self._panels[name] = window

        # guilib.create_window() checks isRunning() on BrowserView.app
        # (= NSApplication.sharedApplication()) and skips app.run() since
        # rumps already started the event loop.
        webview.guilib.create_window(window)

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------

    def open_scribe(self, _: Any = None) -> None:
        """Open the Scribe panel and start recording immediately."""
        existing = self._panels.get("scribe")
        if existing is not None:
            try:
                existing.show()
                return
            except Exception:
                logger.warning("Could not show existing Scribe panel; recreating", exc_info=True)
                self._panels.pop("scribe", None)

        # Reset the controller so a new session starts fresh.
        from liscribe.controllers.scribe_controller import ControllerState
        if self._scribe_ctrl.state != ControllerState.IDLE:
            logger.warning(
                "Scribe panel opened while controller is in state %r; cancelling previous session.",
                self._scribe_ctrl.state.value,
            )
            self._scribe_ctrl.cancel()

        # Start recording before the panel is visible so audio capture
        # begins at the moment the user triggers the panel.
        try:
            self._scribe_ctrl.start()
        except Exception:
            logger.error("Failed to start Scribe recording", exc_info=True)
            return

        self._open_panel(
            "scribe",
            "Scribe",
            width=560,
            height=640,
            js_api=self._scribe_bridge,
        )

    def open_dictate(self, _: Any = None) -> None:
        self._open_panel("dictate", "Dictate", width=320, height=100, resizable=False)

    def open_transcribe(self, _: Any = None) -> None:
        self._open_panel("transcribe", "Transcribe", width=560, height=520)

    def open_settings(self, _: Any = None) -> None:
        self._open_panel("settings", "Settings", width=560, height=580)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)

    config = ConfigService()
    audio = AudioService(config)
    model = ModelService(config)
    hotkey = HotkeyService(config)

    app = LiscribleApp(config=config, audio=audio, model=model, hotkey=hotkey)

    hotkey.start(
        on_scribe=app.open_scribe,
        on_dictate_toggle=lambda: None,
        on_dictate_hold_start=lambda: None,
        on_dictate_hold_end=lambda: None,
    )

    app.run()


if __name__ == "__main__":
    main()
