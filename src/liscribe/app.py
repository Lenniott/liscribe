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

import os
import sys

# Daemonize before any other imports (rumps, webview, etc. start threads; fork is unsafe after that).
# Re-exec this script in a new session so the app keeps running after the terminal is closed.
_DAEMON_ENV = "LISCRIBE_DAEMON"


def _maybe_detach() -> None:
    if os.environ.get(_DAEMON_ENV):
        return
    try:
        if not os.isatty(sys.stdin.fileno()):
            return
    except (AttributeError, OSError):
        return
    pid = os.fork()
    if pid > 0:
        sys.exit(0)
    os.setsid()
    with open(os.devnull, "r") as r:
        os.dup2(r.fileno(), 0)
    with open(os.devnull, "a") as w:
        os.dup2(w.fileno(), 1)
        os.dup2(w.fileno(), 2)
    os.environ[_DAEMON_ENV] = "1"
    os.execv(sys.executable, [sys.executable, __file__] + sys.argv[1:])
    sys.exit(1)


if __name__ == "__main__":
    _maybe_detach()

import logging
from pathlib import Path
from typing import Any

import rumps
import webview
from webview import http as webview_http

import AppKit
from PyObjCTools import AppHelper

from liscribe.bridge.scribe_bridge import ScribeAppActions, ScribeBridge
from liscribe.bridge.transcribe_bridge import TranscribeBridge
from liscribe.controllers.scribe_controller import ControllerState, ScribeController
from liscribe.controllers.transcribe_controller import TranscribeController
from liscribe.services.audio_service import AudioService
from liscribe.services.config_service import ConfigService
from liscribe.services.hotkey_service import HotkeyService
from liscribe.services.model_service import ModelService

logger = logging.getLogger(__name__)

PANELS_DIR = Path(__file__).parent / "ui" / "panels"


def _set_scribe_confirm_close(window: webview.Window, value: bool) -> None:
    """Set confirm_close on the Scribe window so the native close flow shows or skips the dialog.

    pywebview's Cocoa backend reads this attribute at close time. See docs/architecture.md
    (Window options). Mutating the window object is required until pywebview exposes a formal API.
    """
    setattr(window, "confirm_close", value)


if sys.platform != "darwin":
    raise RuntimeError("Liscribe requires macOS.")

# Wire webview's guilib without calling webview.start().
# cocoa.py imports NSApplication.sharedApplication() at class-definition
# time, so guilib is usable as soon as the module is imported.
import webview.platforms.cocoa as _cocoa_guilib  # noqa: E402
from webview.platforms.cocoa import BrowserView  # noqa: E402

webview.guilib = _cocoa_guilib
webview.renderer = _cocoa_guilib.renderer

# Duplicates webview/platforms/cocoa.py BrowserView.WindowDelegate.windowWillClose_.
# We omit app.stop_() so the menu bar app stays running when the last panel closes.
# Fragile on pywebview upgrade — re-check if upgrading pywebview.


def _window_will_close_no_stop(self, notification):
    """Same as pywebview's windowWillClose_ but never stop the app when last window closes."""
    i = BrowserView.get_instance("window", notification.object())
    del BrowserView.instances[i.uid]
    if i.pywebview_window in webview.windows:
        webview.windows.remove(i.pywebview_window)
    i.webview.setNavigationDelegate_(None)
    i.webview.setUIDelegate_(None)
    i.webview.loadHTMLString_baseURL_("", None)
    i.webview.removeFromSuperview()
    i.webview = None
    i.closed.set()
    # Do not call app.stop_() / abortModal(); keep menu bar app running.


_cocoa_guilib.BrowserView.WindowDelegate.windowWillClose_ = _window_will_close_no_stop


class _ScribeAppActionsImpl:
    """Implements ScribeAppActions by delegating to the app's Scribe lifecycle methods."""

    def __init__(self, app: "LiscribleApp") -> None:
        self._app = app

    def close_panel(self) -> None:
        self._app._close_scribe_panel()

    def request_close(self) -> None:
        self._app._request_scribe_close()

    def transcription_finished(self) -> None:
        self._app._scribe_transcription_finished()

    def open_in_transcribe(self, wav_path: str, save_folder: str | None) -> None:
        self._app._open_transcribe_with_prefill(wav_path, output_folder=save_folder)


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

        # Transcribe controller + bridge (Phase 5).
        self._transcribe_ctrl = TranscribeController(config=config, model=model)
        self._transcribe_bridge = TranscribeBridge(
            controller=self._transcribe_ctrl, model=model, config=config
        )

        # Scribe controller + bridge — one instance for the app lifetime.
        self._scribe_ctrl = ScribeController(
            audio=audio, model=model, config=config
        )
        self._scribe_bridge = ScribeBridge(
            controller=self._scribe_ctrl,
            model=model,
            audio=audio,
            app_actions=_ScribeAppActionsImpl(self),
        )

        # name → open webview.Window (None-entry means window was closed)
        self._panels: dict[str, webview.Window] = {}
        # Panel HTML is served over HTTP so WKWebView loads reliably on macOS (file:// can show blank).
        self._panel_http_base: str | None = None
        self._panel_server: webview_http.BottleServer | None = None

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
        """URL for the panel. Prefer HTTP so WKWebView loads reliably on macOS."""
        if self._panel_http_base is not None:
            return f"{self._panel_http_base}panels/{name}.html"
        return (PANELS_DIR / f"{name}.html").as_uri()

    def _ensure_panel_server(self) -> None:
        """Start the static server for panel assets once per app lifetime (see _panel_http_base comment)."""
        if self._panel_http_base is not None:
            return
        ui_dir = str(PANELS_DIR.parent)
        address, _common_path, server = webview_http.BottleServer.start_server(
            [ui_dir], http_port=None
        )
        self._panel_http_base = address
        self._panel_server = server
        logger.debug("Panel HTTP server at %s", address)

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
        # Bring app to front so the panel surfaces above other windows (e.g. terminal).
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._ensure_panel_server()

        existing = self._panels.get(name)
        if existing is not None:
            try:
                existing.show()
                return
            except Exception:
                logger.warning("Could not show existing panel %r; recreating", name, exc_info=True)
                self._panels.pop(name, None)

        create_kwargs: dict[str, Any] = {} if js_api is None else {"js_api": js_api}
        if name == "scribe":
            create_kwargs["confirm_close"] = True  # See _set_scribe_confirm_close and architecture.md
        window = webview.create_window(
            title,
            self._panel_url(name),
            width=width,
            height=height,
            resizable=resizable,
            min_size=(400, 300),
            **create_kwargs,
        )

        def _on_closed() -> None:
            if name == "scribe":
                if self._scribe_ctrl.state == ControllerState.RECORDING:
                    self._scribe_ctrl.cancel()
            self._panels.pop(name, None)

        window.events.closed += _on_closed
        self._panels[name] = window

        # We use guilib.create_window() without webview.start(), so window._initialize()
        # is never run. Set the attributes that Cocoa/inject_pywebview need. Full
        # _initialize() breaks run_js (GUI is not initialized) due to init order.
        if not hasattr(window, "localization"):
            from webview.localization import original_localization
            window.localization = original_localization.copy()
        if name == "scribe":
            window.localization = {
                **window.localization,
                "global.quitConfirmation": "Recording in progress\n\nGo back to recording, or leave and discard?",
                "global.quit": "Leave and discard",
                "global.cancel": "Back",
            }
        if not hasattr(window, "js_api_endpoint"):
            window.js_api_endpoint = None
        if window.gui is None:
            window.gui = webview.guilib
        # Cocoa backend loads window.real_url; without _initialize() it stays None and DEFAULT_HTML is shown.
        window.real_url = window.original_url

        # guilib.create_window() checks isRunning() on BrowserView.app
        # (= NSApplication.sharedApplication()) and skips app.run() since
        # rumps already started the event loop.
        webview.guilib.create_window(window)

        # Phase 5: Transcribe bridge needs window reference for file/folder dialogs.
        if name == "transcribe" and js_api is not None and hasattr(js_api, "set_window"):
            js_api.set_window(window)

    # ------------------------------------------------------------------
    # Menu callbacks
    # ------------------------------------------------------------------

    def open_scribe(self, _: Any = None) -> None:
        """Open the Scribe panel and start recording immediately."""
        existing = self._panels.get("scribe")
        if existing is not None:
            # Reuse existing window: reset controller, start new session, reload page, then show.
            if self._scribe_ctrl.state != ControllerState.IDLE:
                self._scribe_ctrl.cancel()
            try:
                self._scribe_ctrl.start()
            except Exception:
                logger.error("Failed to start Scribe recording", exc_info=True)
                return
            self._ensure_panel_server()
            _set_scribe_confirm_close(existing, True)
            try:
                existing.load_url(self._panel_url("scribe"))
                existing.show()
            except Exception:
                logger.warning("Could not reload/show existing Scribe panel; recreating", exc_info=True)
                self._panels.pop("scribe", None)
                self._scribe_ctrl.cancel()
                # Fall through to create new window once (no recursive retry).
            else:
                return

        # New window or single retry after reload failure.
        if self._scribe_ctrl.state != ControllerState.IDLE:
            logger.warning(
                "Scribe panel opened while controller is in state %r; cancelling previous session.",
                self._scribe_ctrl.state.value,
            )
            self._scribe_ctrl.cancel()

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
        self._open_panel(
            "transcribe",
            "Transcribe",
            width=560,
            height=520,
            js_api=self._transcribe_bridge,
        )

    def _open_transcribe_with_prefill(
        self, audio_path: str, output_folder: str | None = None
    ) -> None:
        """Open the Transcribe panel with audio path and output folder pre-filled (e.g. from Scribe)."""
        self._transcribe_ctrl.set_prefill(
            audio_path=audio_path,
            output_folder=output_folder or self._config.save_folder,
        )
        # Force a fresh panel so get_initial_state() returns the new prefill on load.
        self._panels.pop("transcribe", None)
        self.open_transcribe()

    def _close_scribe_panel(self) -> None:
        """Close the Scribe panel (called from bridge when user chooses Leave and discard)."""
        w = self._panels.get("scribe")
        if w is not None:
            try:
                w.destroy()
            except Exception as exc:
                logger.warning("Could not destroy Scribe panel: %s", exc)
            self._panels.pop("scribe", None)

    def _request_scribe_close(self) -> None:
        """Trigger the native close flow (same confirm dialog as the red X)."""
        w = self._panels.get("scribe")
        if w is None:
            return
        native = getattr(w, "native", None)
        if native is None:
            logger.warning("Scribe window has no native handle for request_close")
            return

        def do_perform_close() -> None:
            try:
                native.performClose_(None)
            except Exception as exc:
                logger.warning("Could not perform close: %s", exc)

        AppHelper.callAfter(do_perform_close)

    def _scribe_transcription_finished(self) -> None:
        """Disable the close warning so the red X just closes (no discard)."""
        w = self._panels.get("scribe")
        if w is not None:
            _set_scribe_confirm_close(w, False)

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
        on_scribe=lambda: AppHelper.callAfter(app.open_scribe),
        on_dictate_toggle=lambda: None,
        on_dictate_hold_start=lambda: None,
        on_dictate_hold_end=lambda: None,
    )

    app.run()


if __name__ == "__main__":
    main()
