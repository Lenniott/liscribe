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

import atexit
import os
import plistlib
import shlex
import subprocess
import sys
import threading

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

from liscribe import app_instance
from liscribe.bridge.dictate_bridge import DictateBridge
from liscribe.bridge.onboarding_bridge import OnboardingBridge
from liscribe.bridge.scribe_bridge import ScribeAppActions, ScribeBridge
from liscribe.bridge.settings_bridge import SettingsBridge
from liscribe.bridge.transcribe_bridge import TranscribeBridge
from liscribe.controllers.dictate_controller import (
    ERROR_NO_MODEL,
    ERROR_SETUP_REQUIRED,
    DictateController,
)
from liscribe.controllers.onboarding_controller import OnboardingController
from liscribe.controllers.scribe_controller import ControllerState, ScribeController
from liscribe.controllers.transcribe_controller import TranscribeController
from liscribe.services.audio_service import AudioService
from liscribe.services.config_service import ConfigService, _get_app_bundle_path
from liscribe.services.hotkey_service import HotkeyService
from liscribe.services.model_service import ModelService
from liscribe.services.permissions_service import has_dictate_permissions

logger = logging.getLogger(__name__)

PANELS_DIR = Path(__file__).parent / "ui" / "panels"

# Panels that, when open, show the app in the Dock. Dictate is excluded (menu bar only when only dictate is open).
DOCK_PANELS = frozenset({"settings", "onboarding", "scribe", "transcribe"})


def _set_scribe_confirm_close(window: webview.Window, value: bool) -> None:
    """Set confirm_close on the Scribe window so the native close flow shows or skips the dialog.

    pywebview's Cocoa backend reads this attribute at close time. See docs/architecture.md
    (Window options). Mutating the window object is required until pywebview exposes a formal API.
    """
    setattr(window, "confirm_close", value)


LAUNCH_AGENT_LABEL = "com.liscribe.restart"


def _schedule_restart_via_launchd(bundle: Path) -> None:
    """Write a one-shot LaunchAgent plist that sleeps 2s, opens the app, then unloads itself.
    The job runs under launchd so it survives when this process exits.
    Uses bootstrap/bootout on macOS (load/unload are deprecated).
    """
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = agents_dir / f"{LAUNCH_AGENT_LABEL}.plist"
    path_str = str(bundle)
    uid = os.getuid()
    domain = f"gui/{uid}"
    script = f"sleep 2; open -a {shlex.quote(path_str)}; launchctl bootout {shlex.quote(domain)} {shlex.quote(LAUNCH_AGENT_LABEL)}"
    plist = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": ["/bin/sh", "-c", script],
        "RunAtLoad": True,
    }
    try:
        # Clear any stale job from a previous run that didn't unload
        subprocess.run(
            ["launchctl", "bootout", domain, LAUNCH_AGENT_LABEL],
            capture_output=True,
            timeout=5,
        )
        with open(plist_path, "wb") as f:
            plistlib.dump(plist, f)
        subprocess.run(
            ["launchctl", "bootstrap", domain, str(plist_path)],
            check=True,
            capture_output=True,
            timeout=5,
        )
    except Exception as exc:
        logger.warning("Failed to schedule restart via launchd: %s", exc)


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
    try:
        i = BrowserView.get_instance("window", notification.object())
    except (KeyError, AttributeError, TypeError) as e:
        logger.warning("windowWillClose: could not get BrowserView instance: %s", e)
        return
    try:
        del BrowserView.instances[i.uid]
    except Exception as e:
        logger.warning("windowWillClose: could not remove BrowserView instance: %s", e)
    if i.pywebview_window in webview.windows:
        webview.windows.remove(i.pywebview_window)
    if i.webview is not None:
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

    def __init__(self, app: "LiscribeApp") -> None:
        self._app = app

    def close_panel(self) -> None:
        self._app._close_scribe_panel()

    def request_close(self) -> None:
        self._app._request_scribe_close()

    def transcription_finished(self) -> None:
        self._app._scribe_transcription_finished()

    def open_in_transcribe(self, wav_path: str, save_folder: str | None) -> None:
        self._app._open_transcribe_with_prefill(wav_path, output_folder=save_folder)


# Menu bar: fallback title when SF Symbol mic icon is unavailable (e.g. macOS < 11).
MENU_BAR_TITLE = "🎙"

APP_DISPLAY_NAME = "Liscribe"


def _set_process_display_name(name: str) -> None:
    """Set the process name so macOS shows it as the app name (menu bar, CMD+Tab, Dock).

    When running as a Python script the process is normally "Python". This uses the
    macOS ApplicationServices API so the app appears as e.g. "Liscribe" instead.
    """
    try:
        from ctypes import Structure, c_int, cdll, pointer
        from ctypes.util import find_library

        lib = find_library("ApplicationServices")
        if not lib:
            return
        app_services = cdll.LoadLibrary(lib)
        GetCurrentProcess = getattr(app_services, "GetCurrentProcess", None)
        CPSSetProcessName = getattr(app_services, "CPSSetProcessName", None)
        if not GetCurrentProcess or not CPSSetProcessName:
            return

        class ProcessSerialNumber(Structure):
            _fields_ = [("highLongOfPSN", c_int), ("lowLongOfPSN", c_int)]

        psn = ProcessSerialNumber()
        if GetCurrentProcess(pointer(psn)) != 0:
            return
        CPSSetProcessName(pointer(psn), name.encode("utf-8"))
    except Exception as exc:
        logger.debug("Could not set process display name: %s", exc)


# Menu bar icon layout: change these to resize the button or the symbol inside it.
_MENUBAR_ICON_WIDTH = 20.0
_MENUBAR_ICON_HEIGHT = 20.0
_MENUBAR_ICON_INSET = 0.0  # Padding around symbol; larger = smaller symbol, more margin.

# Dock icon size (Dock scales down; 256 is enough for sharp display).
_DOCK_ICON_SIZE = 256.0


def _waveform_icon_image(size: float) -> object | None:
    """Return an NSImage: white waveform.and.mic symbol at the given size, or None if unavailable."""
    try:
        symbol = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "waveform.and.mic", None
        )
        if symbol is None:
            return None
        inset = size * 0.1
        rect_size = size - 2 * inset
        img = AppKit.NSImage.alloc().initWithSize_(AppKit.NSMakeSize(size, size))
        img.lockFocus()
        symbol_rect = AppKit.NSMakeRect(inset, inset, rect_size, rect_size)
        AppKit.NSColor.whiteColor().set()
        AppKit.NSRectFill(symbol_rect)
        symbol.drawInRect_fromRect_operation_fraction_(
            symbol_rect,
            AppKit.NSMakeRect(0, 0, symbol.size().width, symbol.size().height),
            AppKit.NSCompositeDestinationIn,
            1.0,
        )
        img.unlockFocus()
        return img
    except (AttributeError, Exception) as exc:
        logger.debug("Could not create waveform icon image: %s", exc)
        return None


def _menubar_icon_image() -> object | None:
    """Return an NSImage: white waveform symbol for the menu bar, or None if unavailable."""
    return _waveform_icon_image(_MENUBAR_ICON_WIDTH)


class LiscribeApp(rumps.App):
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
        super().__init__(MENU_BAR_TITLE, quit_button="Quit")

        icon_nsimage = _menubar_icon_image()
        if icon_nsimage is not None:
            self._icon_nsimage = icon_nsimage
            self._title = ""
            try:
                AppKit.NSApplication.sharedApplication().setApplicationIconImage_(
                    icon_nsimage
                )
            except Exception:
                pass

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

        # Dictate controller + bridge (Phase 6).
        self._dictate_ctrl = DictateController(
            audio=audio,
            model=model,
            config=config,
            can_dictate=has_dictate_permissions,
            on_paste_complete=lambda: AppHelper.callAfter(self._close_dictate_panel),
            run_on_main=AppHelper.callAfter,
        )
        self._dictate_bridge = DictateBridge(
            controller=self._dictate_ctrl,
            on_open_settings_help=lambda anchor: AppHelper.callAfter(
                self.open_settings_to_help, anchor
            ),
        )

        self._settings_bridge = SettingsBridge(
            config=config,
            model=model,
            audio=audio,
            on_close=lambda: AppHelper.callAfter(self._close_settings_panel),
            on_restart=lambda: AppHelper.callAfter(self._schedule_restart),
            # Reserved for future in-process hotkey reload when safe on macOS; not called by bridge (changes apply after full restart).
            on_launch_hotkey_changed=lambda: threading.Thread(
                target=self._hotkey.restart_scribe_listener, daemon=True, name="restart-scribe-hotkey"
            ).start(),
            on_dictation_hotkey_changed=lambda: threading.Thread(
                target=self._hotkey.restart_dictate_listener, daemon=True, name="restart-dictate-hotkey"
            ).start(),
            on_replay_setup_guide=lambda: AppHelper.callAfter(self.open_onboarding),
        )

        # Onboarding (Phase 8)
        self._onboarding_ctrl = OnboardingController(config=config, model=model)
        sample_path = self._onboarding_ctrl.get_sample_audio_path()
        self._onboarding_bridge = OnboardingBridge(
            controller=self._onboarding_ctrl,
            on_open_scribe=lambda: AppHelper.callAfter(self.open_scribe),
            on_open_transcribe_with_sample=lambda: AppHelper.callAfter(
                lambda: self._open_transcribe_with_prefill(str(sample_path))
            ),
            on_onboarding_complete=lambda: AppHelper.callAfter(self._close_onboarding_panel),
            on_open_help=lambda anchor: AppHelper.callAfter(self.open_settings_to_help, anchor or "permissions"),
            on_open_settings_general=lambda: AppHelper.callAfter(self._open_settings_from_onboarding),
            on_relaunch=lambda: AppHelper.callAfter(self._schedule_restart),
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

    def _update_dock_visibility(self) -> None:
        """Show app in Dock when any of settings/onboarding/scribe/transcribe is open; hide when none."""
        nsapp = AppKit.NSApplication.sharedApplication()
        if any(p in self._panels for p in DOCK_PANELS):
            nsapp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
            # Use same waveform icon as menu bar but at Dock size; set on app and dock tile so Dock updates.
            dock_icon = getattr(self, "_dock_icon_nsimage", None)
            if dock_icon is None:
                dock_icon = _waveform_icon_image(_DOCK_ICON_SIZE)
                if dock_icon is not None:
                    self._dock_icon_nsimage = dock_icon
            if dock_icon is not None:
                try:
                    nsapp.setApplicationIconImage_(dock_icon)
                    dock_tile = nsapp.dockTile()
                    if dock_tile is not None:
                        dock_tile.setIcon_(dock_icon)
                        dock_tile.display()
                except Exception:
                    pass
            _set_process_display_name(APP_DISPLAY_NAME)
        else:
            nsapp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

    def _panel_url(self, name: str, fragment: str | None = None) -> str:
        """URL for the panel. Prefer HTTP so WKWebView loads reliably on macOS."""
        if self._panel_http_base is not None:
            base = f"{self._panel_http_base}panels/{name}.html"
        else:
            base = (PANELS_DIR / f"{name}.html").as_uri()
        if fragment:
            return base + "#" + fragment
        return base

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
        fragment: str | None = None,
    ) -> None:
        """Open a named panel, raising it if already open. fragment is optional hash (e.g. help/accessibility)."""
        # Bring app to front so the panel surfaces above other windows (e.g. terminal).
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._ensure_panel_server()

        existing = self._panels.get(name)
        if existing is not None:
            try:
                if fragment and name == "settings":
                    existing.load_url(self._panel_url(name, fragment=fragment))
                existing.show()
                return
            except Exception:
                logger.warning("Could not show existing panel %r; recreating", name, exc_info=True)
                self._panels.pop(name, None)

        create_kwargs: dict[str, Any] = {} if js_api is None else {"js_api": js_api}
        if name == "scribe":
            create_kwargs["confirm_close"] = True  # See _set_scribe_confirm_close and architecture.md
        url = self._panel_url(name, fragment=fragment)
        window = webview.create_window(
            title,
            url,
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
            # Resign active and bring the app that was behind (e.g. Cursor) to the front so the user can click and type.
            if name == "scribe":
                AppHelper.callAfter(lambda: AppKit.NSApplication.sharedApplication().hide_(None))
            AppHelper.callAfter(self._update_dock_visibility)

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

        if name in DOCK_PANELS:
            AppHelper.callAfter(self._update_dock_visibility)

        # Phase 5: Transcribe bridge needs window reference for file/folder dialogs.
        if name == "transcribe" and js_api is not None and hasattr(js_api, "set_window"):
            js_api.set_window(window)
        # Phase 7: Settings bridge needs window for pick_folder, pick_app, navigate_help.
        if name == "settings" and js_api is not None and hasattr(js_api, "set_window"):
            js_api.set_window(window)
        # Phase 8: Onboarding bridge needs window for pick_app (Choose application).
        if name == "onboarding" and js_api is not None and hasattr(js_api, "set_window"):
            js_api.set_window(window)

    def _schedule_restart(self) -> None:
        """Quit and relaunch the app. Uses a launchd one-shot job when running as .app so the
        restarter is not our child and survives when we exit.
        """
        bundle = _get_app_bundle_path()
        if bundle:
            _schedule_restart_via_launchd(bundle)
        else:
            # Dev mode: subprocess may be killed when we quit; launchd not used.
            subprocess.Popen(
                ["/bin/sh", "-c", "(sleep 2; exec \"$0\" -m liscribe ${1+\"$@\"}) &", sys.executable] + sys.argv[1:],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        AppHelper.callAfter(lambda: AppKit.NSApplication.sharedApplication().terminate_(None))

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
        """Open the Dictate panel and start recording if idle (menu or hotkey)."""
        self._hotkey.start_dictate_listener()
        if self._dictate_ctrl.is_recording:
            x, y = self._cursor_position_for_panel(panel_width=320, panel_height=100)
            self._open_dictate_panel(x=x, y=y)
        else:
            self._on_dictate_trigger("handle_toggle")

    def _open_dictate_panel(self, x: int | None = None, y: int | None = None) -> None:
        """Create or show the Dictate panel window at the given screen position."""
        existing = self._panels.get("dictate")
        if existing is not None:
            try:
                existing.show()
                return
            except Exception:
                logger.warning("Could not show existing Dictate panel; recreating", exc_info=True)
                self._panels.pop("dictate", None)

        self._ensure_panel_server()
        create_kwargs: dict[str, Any] = {"js_api": self._dictate_bridge}
        if x is not None:
            create_kwargs["x"] = x
        if y is not None:
            create_kwargs["y"] = y

        window = webview.create_window(
            "Dictate",
            self._panel_url("dictate"),
            width=320,
            height=100,
            resizable=False,
            on_top=True,
            min_size=(200, 80),
            **create_kwargs,
        )

        def _on_closed() -> None:
            self._panels.pop("dictate", None)

        window.events.closed += _on_closed
        self._panels["dictate"] = window

        if not hasattr(window, "localization"):
            from webview.localization import original_localization
            window.localization = original_localization.copy()
        if not hasattr(window, "js_api_endpoint"):
            window.js_api_endpoint = None
        if window.gui is None:
            window.gui = webview.guilib
        window.real_url = window.original_url

        webview.guilib.create_window(window)

    def _cursor_position_for_panel(
        self, panel_width: int = 320, panel_height: int = 100
    ) -> tuple[int, int]:
        """Return (x, y) screen coords to place a panel near the mouse cursor.

        Adjusts so the panel stays on screen. Falls back to (100, 100) on error.
        """
        try:
            # NSEvent.mouseLocation() returns Cocoa coordinates (origin = bottom-left).
            # Convert to top-left origin for pywebview by subtracting from screen height.
            mouse = AppKit.NSEvent.mouseLocation()
            screen = AppKit.NSScreen.mainScreen().frame()
            screen_h = int(screen.size.height)
            screen_w = int(screen.size.width)

            x = int(mouse.x) + 12  # offset right of cursor
            y = screen_h - int(mouse.y) - panel_height - 12  # convert Y + offset below cursor

            # Clamp so panel stays on screen.
            x = max(0, min(x, screen_w - panel_width))
            y = max(0, min(y, screen_h - panel_height))
            return x, y
        except Exception:
            logger.debug("Could not read cursor position for Dictate panel", exc_info=True)
            return 100, 100

    # ------------------------------------------------------------------
    # Dictate hotkey callbacks (called from hotkey service)
    # ------------------------------------------------------------------

    def _on_dictate_trigger(self, handler_name: str) -> None:
        """Call the controller, show panel or Setup Required modal."""
        ctrl = self._dictate_ctrl
        handler = getattr(ctrl, handler_name)
        result = handler()
        if not result.get("ok"):
            error = result.get("error")
            if error == ERROR_SETUP_REQUIRED:
                missing = result.get("missing_permissions", [])
                AppHelper.callAfter(self._show_dictate_setup_required, missing)
            elif error == ERROR_NO_MODEL:
                model = result.get("model", "base")
                AppHelper.callAfter(
                    self._show_notification,
                    "Dictate — model not downloaded",
                    f"Download the '{model}' model in Settings → Models.",
                )
            else:
                AppHelper.callAfter(
                    self._show_notification, "Dictate error", str(error or "Unknown error")
                )
            return

        if ctrl.is_recording:
            x, y = self._cursor_position_for_panel(320, 100)
            AppHelper.callAfter(self._open_dictate_panel, x, y)

    def _on_dictate_stop_if_recording(self) -> None:
        """Stop a toggle-mode recording on single ^ press. Does nothing when idle."""
        if self._dictate_ctrl.is_recording:
            self._on_dictate_trigger("handle_toggle")

    def _on_dictate_toggle(self) -> None:
        self._on_dictate_trigger("handle_toggle")

    def _on_dictate_hold_start(self) -> None:
        self._on_dictate_trigger("handle_hold_start")

    def _on_dictate_hold_end(self) -> None:
        self._on_dictate_trigger("handle_hold_end")

    def _close_dictate_panel(self) -> None:
        w = self._panels.get("dictate")
        if w is not None:
            try:
                w.destroy()
            except Exception as exc:
                logger.warning("Could not destroy Dictate panel: %s", exc)
            self._panels.pop("dictate", None)

    def _close_settings_panel(self) -> None:
        """Close the Settings panel (called from bridge when user clicks header close)."""
        w = self._panels.get("settings")
        if w is not None:
            try:
                w.destroy()
            except Exception as exc:
                logger.warning("Could not destroy Settings panel: %s", exc)
            self._panels.pop("settings", None)

    def _close_onboarding_panel(self) -> None:
        """Close the onboarding panel (called from bridge when user completes step 8)."""
        w = self._panels.get("onboarding")
        if w is not None:
            try:
                w.destroy()
            except Exception as exc:
                logger.warning("Could not destroy Onboarding panel: %s", exc)
            self._panels.pop("onboarding", None)

    def _open_onboarding_panel(self) -> None:
        """Open the onboarding panel (first-launch or replay from Settings)."""
        existing = self._panels.get("onboarding")
        if existing is not None:
            try:
                existing.show()
                return
            except Exception:
                self._panels.pop("onboarding", None)
        self._open_panel(
            "onboarding",
            "Welcome to Liscribe",
            width=560,
            height=580,
            js_api=self._onboarding_bridge,
        )

    def _maybe_show_onboarding(self, _timer: Any = None) -> None:
        """If onboarding not complete, open the onboarding panel. Called once after app start."""
        if _timer is not None:
            try:
                _timer.stop()
            except Exception:
                pass
        if not self._config.onboarding_complete:
            self._open_onboarding_panel()

    def open_onboarding(self) -> None:
        """Open onboarding from Settings (Replay setup guide). Resets to step 1 and opens panel."""
        self._onboarding_ctrl.reset_for_replay()
        self._open_onboarding_panel()

    def _show_notification(self, title: str, message: str) -> None:
        try:
            import rumps
            rumps.notification(title, "", message, sound=False)
        except Exception:
            logger.debug("Could not show notification: %s — %s", title, message, exc_info=True)

    def _show_dictate_setup_required(self, missing: list[str]) -> None:
        """Show the Setup Required modal for missing Dictate permissions.

        Opens the dictate.html panel in setup-required mode by passing the
        missing permission list as a query parameter.
        """
        names = ",".join(missing)
        self._ensure_panel_server()
        base_url = self._panel_url("dictate")
        url = f"{base_url}?setup_required={names}"

        existing = self._panels.get("dictate")
        if existing is not None:
            try:
                existing.load_url(url)
                existing.show()
                return
            except Exception:
                self._panels.pop("dictate", None)

        window = webview.create_window(
            "Setup Required",
            url,
            width=460,
            height=320,
            resizable=False,
        )

        def _on_closed() -> None:
            self._panels.pop("dictate", None)

        window.events.closed += _on_closed
        self._panels["dictate"] = window

        if not hasattr(window, "localization"):
            from webview.localization import original_localization
            window.localization = original_localization.copy()
        if not hasattr(window, "js_api_endpoint"):
            window.js_api_endpoint = None
        if window.gui is None:
            window.gui = webview.guilib
        window.real_url = window.original_url

        webview.guilib.create_window(window)

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

    def _open_settings_from_onboarding(self) -> None:
        """Close onboarding (if open) and open Settings with the General tab selected."""
        self._close_onboarding_panel()
        self._open_panel(
            "settings",
            "Settings",
            width=560,
            height=580,
            js_api=self._settings_bridge,
            fragment="general",
        )

    def open_settings(self, _: Any = None) -> None:
        """Open Settings panel. Wrapped so an exception here does not quit the app."""
        try:
            self._open_panel(
                "settings",
                "Settings",
                width=560,
                height=580,
                js_api=self._settings_bridge,
            )
        except Exception as exc:
            logger.exception("Failed to open Settings panel: %s", exc)
            try:
                msg = str(exc)[:80] if str(exc) else "See console for details."
                rumps.notification(
                    "Liscribe",
                    "Could not open Settings",
                    msg,
                    sound=False,
                )
            except Exception:
                pass

    def open_settings_to_help(self, anchor: str) -> None:
        """Open Settings panel and navigate to the given Help section (e.g. permissions, blackhole)."""
        self._open_panel(
            "settings",
            "Settings",
            width=560,
            height=580,
            js_api=self._settings_bridge,
            fragment="help/" + (anchor or "permissions"),
        )


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    _set_process_display_name(APP_DISPLAY_NAME)

    def activate_on_main_thread() -> None:
        AppKit.NSApplication.sharedApplication().activateIgnoringOtherApps_(True)

    guard = app_instance.acquire(
        on_activate=lambda: AppHelper.callAfter(activate_on_main_thread)
    )
    if guard is None:
        app_instance.try_activate_existing()
        sys.exit(0)
    atexit.register(guard.release)

    config = ConfigService()
    audio = AudioService(config)
    model = ModelService(config)
    hotkey = HotkeyService(config)

    app = LiscribeApp(config=config, audio=audio, model=model, hotkey=hotkey)

    hotkey.start(
        on_scribe=lambda: AppHelper.callAfter(app.open_scribe),
        on_dictate_toggle=lambda: AppHelper.callAfter(app._on_dictate_trigger, "handle_toggle"),
        on_dictate_hold_start=lambda: AppHelper.callAfter(app._on_dictate_trigger, "handle_hold_start"),
        on_dictate_hold_end=lambda: AppHelper.callAfter(app._on_dictate_trigger, "handle_hold_end"),
        on_dictate_single_release=lambda: AppHelper.callAfter(app._on_dictate_stop_if_recording),
        get_is_toggle_recording=lambda: app._dictate_ctrl.is_toggle_recording,
    )

    # Start the dictate key listener immediately if permissions are already granted.
    # This lets ^^ work without requiring the user to open Dictate from the menu first.
    # open_dictate() also calls start_dictate_listener() as a fallback for the case
    # where permissions are granted later (or this call was skipped due to an error).
    try:
        ok, missing = has_dictate_permissions()
        if ok:
            hotkey.start_dictate_listener()
    except Exception:
        logger.warning("Could not start dictate key listener at startup", exc_info=True)

    # Dock: suppress when onboarding already complete; show with correct icon/name when onboarding will run.
    nsapp = AppKit.NSApplication.sharedApplication()
    if config.onboarding_complete:
        nsapp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    else:
        nsapp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
        dock_icon = _waveform_icon_image(_DOCK_ICON_SIZE)
        if dock_icon is not None:
            try:
                nsapp.setApplicationIconImage_(dock_icon)
                dock_tile = nsapp.dockTile()
                if dock_tile is not None:
                    dock_tile.setIcon_(dock_icon)
                    dock_tile.display()
            except Exception:
                pass
        _set_process_display_name(APP_DISPLAY_NAME)

    # First launch: show onboarding if not yet complete (one-shot after 0.5s).
    def _on_first_show(sender: Any) -> None:
        try:
            sender.stop()
        except Exception:
            pass
        app._maybe_show_onboarding()

    _first_show_timer = rumps.Timer(_on_first_show, 0.5)
    _first_show_timer.start()

    app.run()


if __name__ == "__main__":
    main()
