"""Global hotkey listener using pynput.

Fires registered callbacks for:
  - scribe_trigger        : ⌃⌥L (or configured combo) — opens Scribe panel
  - on_dictate_toggle     : double-tap — start toggle recording
  - on_dictate_hold_start : key held past threshold — start hold recording
  - on_dictate_hold_end   : held key released — stop hold recording
  - on_dictate_single_release : press + release while in toggle recording — stop toggle

Two listeners run in daemon threads:
  1. GlobalHotKeys — for the Scribe combo (⌃⌥L or user-configured)
  2. keyboard.Listener — for the Dictate key (press/release; key is
     user-configured via config.dictation_hotkey)

Dictate key state machine
─────────────────────────
The listener has three internal phases. Which phase applies is determined on
each press by querying `_get_is_toggle_recording()` (injected from app.py so
the hotkey service never imports the controller directly).

Phase A — IDLE / AFTER FIRST TAP
  Press  → start hold timer.
  Release before hold timer fires (quick tap):
    If this was the first tap → set _after_first_tap, wait for second press.
    If _after_first_tap was set → second quick tap → fire on_dictate_toggle (toggle recording).
  Hold timer fires (no release):
    If _after_first_tap → tap-then-hold → fire on_dictate_hold_start (Phase C).
    Otherwise (long first press from idle) → ignore.

Phase B — TOGGLE RECORDING (started by double-tap; controller is in toggle mode)
  Press  → set _expect_release_to_stop; ignore hold/double-tap logic.
  Release → fire on_dictate_single_release; clear flag.

Phase C — HOLD RECORDING (started by hold timer in Phase A)
  Press  → ignore (key repeat while held).
  Release → fire on_dictate_hold_end; back to IDLE.
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from liscribe.services.config_service import ConfigService

logger = logging.getLogger(__name__)

try:
    from pynput import keyboard as pynput_keyboard
    _PYNPUT_AVAILABLE = True
except ImportError:
    _PYNPUT_AVAILABLE = False
    logger.warning("pynput not available; global hotkeys will be disabled")

# Map config dictation_hotkey string values → pynput Key names.
_DICTATE_KEY_MAP: dict[str, str] = {
    "right_option": "alt_r",
    "right_ctrl": "ctrl_r",
    # macOS pynput reports both Left and Right Control as Key.ctrl.
    "left_ctrl": "ctrl",
    "right_shift": "shift_r",
    "caps_lock": "caps_lock",
}

# Seconds the second press must be held (without release) to enter hold-recording mode.
# A second press released before this threshold counts as a double-tap (toggle recording).
_HOLD_THRESHOLD = 0.40


class HotkeyService:
    """pynput-based global hotkey listener.

    One instance, created in app.py and started once.
    """

    def __init__(self, config: ConfigService) -> None:
        self._config = config
        self._listener: object | None = None
        self._listener_thread: threading.Thread | None = None
        self._dictate_listener: object | None = None
        self._dictate_listener_thread: threading.Thread | None = None

        # Callbacks wired from app.py
        self._on_scribe: Callable[[], None] = lambda: None
        self._on_dictate_toggle: Callable[[], None] = lambda: None
        self._on_dictate_hold_start: Callable[[], None] = lambda: None
        self._on_dictate_hold_end: Callable[[], None] = lambda: None
        self._on_dictate_single_release: Callable[[], None] = lambda: None
        # Query injected from app: True when controller is in toggle-mode recording.
        self._get_is_toggle_recording: Callable[[], bool] = lambda: False

        # State machine variables
        self._after_first_tap: bool = False            # True after one quick tap; waiting for second press
        self._hold_timer: threading.Timer | None = None      # fires after _HOLD_THRESHOLD if key still down
        self._in_hold_recording: bool = False          # True while hold recording (between hold_start and hold_end)
        self._expect_release_to_stop: bool = False     # True when next release should fire single_release

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(
        self,
        on_scribe: Callable[[], None] | None = None,
        on_dictate_toggle: Callable[[], None] | None = None,
        on_dictate_hold_start: Callable[[], None] | None = None,
        on_dictate_hold_end: Callable[[], None] | None = None,
        on_dictate_single_release: Callable[[], None] | None = None,
        get_is_toggle_recording: Callable[[], bool] | None = None,
    ) -> None:
        """Register callbacks and start the Scribe hotkey listener."""
        if on_scribe:
            self._on_scribe = on_scribe
        if on_dictate_toggle:
            self._on_dictate_toggle = on_dictate_toggle
        if on_dictate_hold_start:
            self._on_dictate_hold_start = on_dictate_hold_start
        if on_dictate_hold_end:
            self._on_dictate_hold_end = on_dictate_hold_end
        if on_dictate_single_release:
            self._on_dictate_single_release = on_dictate_single_release
        if get_is_toggle_recording:
            self._get_is_toggle_recording = get_is_toggle_recording

        if not _PYNPUT_AVAILABLE:
            return

        self._listener_thread = threading.Thread(
            target=self._run_listener, daemon=True, name="hotkey-listener"
        )
        self._listener_thread.start()

        # Dictate listener started lazily to avoid aborting on macOS when Input
        # Monitoring permission has not been granted yet.
        self._dictate_listener_thread = None

    def start_dictate_listener(self) -> None:
        """Start the dictate key listener if not already running.

        Safe to call multiple times. Called when the user first opens Dictate
        (either from the menu or via startup permission check) so pynput.Listener
        is not created at process startup before Input Monitoring is granted.
        """
        if not _PYNPUT_AVAILABLE:
            return
        if self._dictate_listener_thread is not None and self._dictate_listener_thread.is_alive():
            return
        self._dictate_listener_thread = threading.Thread(
            target=self._run_dictate_listener, daemon=True, name="dictate-key-listener"
        )
        self._dictate_listener_thread.start()

    def stop(self) -> None:
        for listener in (self._listener, self._dictate_listener):
            if listener is not None:
                try:
                    listener.stop()  # type: ignore[attr-defined]
                except Exception:
                    logger.warning("Error stopping hotkey listener", exc_info=True)
        self._listener = None
        self._dictate_listener = None

    # ------------------------------------------------------------------
    # Scribe listener
    # ------------------------------------------------------------------

    def _run_listener(self) -> None:
        if not _PYNPUT_AVAILABLE:
            return
        scribe_combo = self._config.get("launch_hotkey") or "<ctrl>+<alt>+l"
        try:
            with pynput_keyboard.GlobalHotKeys({scribe_combo: self._on_scribe}) as listener:
                self._listener = listener
                listener.join()
        except Exception:
            logger.warning("Scribe hotkey listener exited with error", exc_info=True)

    # ------------------------------------------------------------------
    # Dictate listener
    # ------------------------------------------------------------------

    def _resolve_dictate_key(self) -> object | None:
        if not _PYNPUT_AVAILABLE:
            return None
        hotkey_name = self._config.dictation_hotkey or "left_ctrl"
        pynput_name = _DICTATE_KEY_MAP.get(hotkey_name)
        if pynput_name is None:
            logger.warning("Unknown dictation_hotkey %r — listener not started", hotkey_name)
            return None
        try:
            return getattr(pynput_keyboard.Key, pynput_name)
        except AttributeError:
            logger.warning("pynput has no Key.%s — listener not started", pynput_name)
            return None

    def _run_dictate_listener(self) -> None:
        if not _PYNPUT_AVAILABLE:
            return
        dictate_key = self._resolve_dictate_key()
        if dictate_key is None:
            return

        def _on_press(key: object) -> None:
            if key == dictate_key:
                self._on_dictate_key_press()

        def _on_release(key: object) -> None:
            if key == dictate_key:
                self._on_dictate_key_release()

        try:
            with pynput_keyboard.Listener(on_press=_on_press, on_release=_on_release) as listener:
                self._dictate_listener = listener
                listener.join()
        except Exception:
            logger.warning("Dictate key listener exited with error", exc_info=True)

    # ------------------------------------------------------------------
    # Dictate key state machine
    # ------------------------------------------------------------------

    def _on_dictate_key_press(self) -> None:
        """Handle a dictate key press event."""
        # Phase B — toggle recording: next release should stop it.
        if self._get_is_toggle_recording():
            self._expect_release_to_stop = True
            return

        # Phase C — hold recording: ignore key repeat while held.
        if self._in_hold_recording:
            return

        # Key repeat while waiting for hold threshold: ignore.
        if self._hold_timer is not None:
            return

        # Start hold timer for this press (works for both first and second press).
        # Whether it's the first or second press is tracked by _after_first_tap.
        self._hold_timer = threading.Timer(_HOLD_THRESHOLD, self._trigger_hold_mode)
        self._hold_timer.daemon = True
        self._hold_timer.start()

    def _trigger_hold_mode(self) -> None:
        """Hold timer fired: key has been held past threshold."""
        self._hold_timer = None
        if self._after_first_tap:
            # Tap then hold → start hold recording.
            self._after_first_tap = False
            self._in_hold_recording = True
            self._on_dictate_hold_start()
        # else: long first press from idle → ignore (tap is required first).

    def _on_dictate_key_release(self) -> None:
        """Handle a dictate key release event."""
        # Phase B — stop toggle recording.
        if self._expect_release_to_stop:
            self._expect_release_to_stop = False
            self._on_dictate_single_release()
            return

        # Phase C — end hold recording.
        if self._in_hold_recording:
            self._in_hold_recording = False
            self._on_dictate_hold_end()
            return

        # Quick release (before hold threshold fired).
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer = None
            if self._after_first_tap:
                # Second quick tap → start toggle recording.
                self._after_first_tap = False
                self._on_dictate_toggle()
            else:
                # First quick tap → now waiting for second press.
                self._after_first_tap = True
