"""Global hotkey listener using pynput.

Fires registered callbacks for:
  - scribe_trigger      : ⌃⌥L (or configured combo) — opens Scribe panel
  - dictate_toggle      : double-tap of configured key — toggle Dictate on/off
  - dictate_hold_start  : key held past debounce threshold — Dictate while held
  - dictate_hold_end    : held key released — stop Dictate

Phase 3: listener starts with scribe_trigger wired; dictate callbacks are
registered here but the raw key-press/release events that drive them are
connected in Phase 6 (DictateController).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from liscribe.services.config_service import ConfigService

logger = logging.getLogger(__name__)

try:
    from pynput import keyboard as pynput_keyboard
    _PYNPUT_AVAILABLE = True
except ImportError:
    _PYNPUT_AVAILABLE = False
    logger.warning("pynput not available; global hotkeys will be disabled")

_DOUBLE_TAP_WINDOW = 0.35  # seconds between two taps to count as double-tap
_HOLD_THRESHOLD = 0.35      # seconds held before switching to hold mode


class HotkeyService:
    """pynput-based global hotkey listener.

    One instance, created in app.py and started once.
    """

    def __init__(self, config: ConfigService) -> None:
        self._config = config
        self._listener: object | None = None
        self._listener_thread: threading.Thread | None = None

        self._on_scribe: Callable[[], None] = lambda: None
        self._on_dictate_toggle: Callable[[], None] = lambda: None
        self._on_dictate_hold_start: Callable[[], None] = lambda: None
        self._on_dictate_hold_end: Callable[[], None] = lambda: None

        # Dictate double-tap / hold state
        self._last_tap_time: float = 0.0
        self._hold_timer: threading.Timer | None = None
        self._in_hold_mode: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        on_scribe: Callable[[], None] | None = None,
        on_dictate_toggle: Callable[[], None] | None = None,
        on_dictate_hold_start: Callable[[], None] | None = None,
        on_dictate_hold_end: Callable[[], None] | None = None,
    ) -> None:
        """Start the global keyboard listener in a daemon thread."""
        if on_scribe:
            self._on_scribe = on_scribe
        if on_dictate_toggle:
            self._on_dictate_toggle = on_dictate_toggle
        if on_dictate_hold_start:
            self._on_dictate_hold_start = on_dictate_hold_start
        if on_dictate_hold_end:
            self._on_dictate_hold_end = on_dictate_hold_end

        if not _PYNPUT_AVAILABLE:
            return

        self._listener_thread = threading.Thread(
            target=self._run_listener, daemon=True, name="hotkey-listener"
        )
        self._listener_thread.start()

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()  # type: ignore[attr-defined]
            except Exception:
                logger.warning("Error stopping hotkey listener", exc_info=True)
        self._listener = None

    # ------------------------------------------------------------------
    # Listener implementation
    # ------------------------------------------------------------------

    def _run_listener(self) -> None:
        if not _PYNPUT_AVAILABLE:
            return

        scribe_combo = self._config.get("launch_hotkey") or "<ctrl>+<alt>+l"
        hotkeys = {scribe_combo: self._on_scribe}

        try:
            with pynput_keyboard.GlobalHotKeys(hotkeys) as listener:
                self._listener = listener
                listener.join()
        except Exception:
            logger.warning("Hotkey listener exited with error", exc_info=True)

    # ------------------------------------------------------------------
    # Dictate key state machine (connected in Phase 6 via DictateController)
    # ------------------------------------------------------------------

    def _on_dictate_key_press(self) -> None:
        """Call when the configured dictate key is pressed."""
        now = time.monotonic()
        elapsed = now - self._last_tap_time

        if self._hold_timer is not None:
            self._hold_timer.cancel()

        if elapsed < _DOUBLE_TAP_WINDOW and not self._in_hold_mode:
            self._last_tap_time = 0.0
            self._on_dictate_toggle()
        else:
            self._last_tap_time = now
            self._in_hold_mode = False
            self._hold_timer = threading.Timer(
                _HOLD_THRESHOLD, self._trigger_hold_mode
            )
            self._hold_timer.daemon = True
            self._hold_timer.start()

    def _trigger_hold_mode(self) -> None:
        self._in_hold_mode = True
        self._on_dictate_hold_start()

    def _on_dictate_key_release(self) -> None:
        """Call when the configured dictate key is released."""
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer = None
        if self._in_hold_mode:
            self._in_hold_mode = False
            self._on_dictate_hold_end()
