"""Dictate workflow controller.

Hotkey state machine (double-tap toggle + hold) → record → transcribe → paste.

State machine:
    IDLE → (handle_toggle or handle_hold_start) → RECORDING
    RECORDING → (handle_toggle [toggle mode] or handle_hold_end [hold mode]) → IDLE
                + background thread: stop audio → transcribe → paste

Design notes:
    - can_dictate is injected (defaults to real OS check) so tests can mock it.
    - Paste helpers (_has_external_focus, _simulate_paste, _simulate_enter, _notify)
      are module-level functions so tests can patch them individually.
    - No direct engine imports; services wrap all engine access.
    - Word replacements (Phase 10) applied before paste in _stop_transcribe_paste.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
import time
from enum import Enum
from typing import TYPE_CHECKING, Callable

from liscribe import replacements as _replacements

if TYPE_CHECKING:
    from liscribe.services.audio_service import AudioService
    from liscribe.services.config_service import ConfigService
    from liscribe.services.model_service import ModelService

logger = logging.getLogger(__name__)

# Error kinds returned in controller result dicts; app.py branches on these.
ERROR_SETUP_REQUIRED = "setup_required"
ERROR_NO_MODEL = "no_model"


class DictateState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


# ---------------------------------------------------------------------------
# Module-level helpers (patchable in tests)
# ---------------------------------------------------------------------------


def _get_frontmost_bundle_id() -> str | None:
    """Return the bundle ID of the current frontmost non-Liscribe app, or None."""
    try:
        import AppKit

        workspace = AppKit.NSWorkspace.sharedWorkspace()
        frontmost = workspace.frontmostApplication()
        if frontmost is None:
            return None
        bundle_id = frontmost.bundleIdentifier() or ""
        if not bundle_id or "python" in bundle_id.lower():
            return None
        return bundle_id
    except Exception:
        logger.debug("_get_frontmost_bundle_id failed", exc_info=True)
        return None


def _activate_bundle(bundle_id: str) -> None:
    """Bring the app with the given bundle ID to the foreground."""
    try:
        import AppKit

        for app in AppKit.NSWorkspace.sharedWorkspace().runningApplications():
            if app.bundleIdentifier() == bundle_id:
                app.activateWithOptions_(
                    AppKit.NSApplicationActivateIgnoringOtherApps
                )
                # Brief pause so the OS focus transfer settles before key simulation.
                time.sleep(0.08)
                break
    except Exception:
        logger.debug("_activate_bundle failed for %r", bundle_id, exc_info=True)


def _simulate_paste() -> None:
    """Simulate Cmd+V using pynput keyboard controller."""
    try:
        from pynput.keyboard import Controller, Key

        kb = Controller()
        with kb.pressed(Key.cmd):
            kb.press("v")
            kb.release("v")
    except Exception:
        logger.debug("_simulate_paste failed", exc_info=True)
        raise


def _simulate_enter() -> None:
    """Simulate the Return key using pynput keyboard controller."""
    try:
        from pynput.keyboard import Controller, Key

        kb = Controller()
        kb.press(Key.enter)
        kb.release(Key.enter)
    except Exception:
        logger.debug("_simulate_enter failed", exc_info=True)
        raise


def _notify(title: str, message: str) -> None:
    """Show a macOS notification. Fails silently if rumps is unavailable."""
    try:
        import rumps

        rumps.notification(title, "", message, sound=False)
    except Exception:
        logger.debug("_notify failed: %s — %s", title, message, exc_info=True)


def _post_webhook_dictate(
    url: str, text: str, recording_start: float | None,
    auth_header_name: str = "", auth_header_value: str = "",
) -> None:
    """Fire-and-forget POST of dictate result to webhook URL. Logs on failure."""
    from liscribe import webhook as _webhook

    duration = (
        round(time.monotonic() - recording_start, 1) if recording_start is not None else 0.0
    )
    _webhook.send_dictation(
        url,
        text,
        duration_seconds=duration,
        auth_header_name=auth_header_name,
        auth_header_value=auth_header_value,
    )


# ---------------------------------------------------------------------------
# Default permission check (replaced in tests via can_dictate= argument)
# ---------------------------------------------------------------------------


def _default_can_dictate() -> tuple[bool, list[str]]:
    from liscribe.services.permissions_service import has_dictate_permissions

    return has_dictate_permissions()


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


class DictateController:
    """Orchestrates one Dictate session.

    Receives all services as constructor arguments — never instantiates them.
    The bridge calls this controller; the controller calls services.

    Thread safety: state transitions are guarded by _lock. The background
    worker thread (_stop_transcribe_paste) reads _state only after the lock
    has already set it to IDLE, so it never races with new triggers.
    """

    def __init__(
        self,
        audio: "AudioService",
        model: "ModelService",
        config: "ConfigService",
        can_dictate: Callable[[], tuple[bool, list[str]]] | None = None,
        on_paste_complete: Callable[[], None] | None = None,
        run_on_main: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self._audio = audio
        self._model = model
        self._config = config
        self._can_dictate = can_dictate or _default_can_dictate
        self._on_paste_complete = on_paste_complete
        self._run_on_main = run_on_main

        self._state = DictateState.IDLE
        self._is_hold_mode: bool = False
        self._start_time: float | None = None
        self._lock = threading.Lock()
        self._last_worker: threading.Thread | None = None
        self._target_bundle_id: str | None = None
        self._dictate_temp_dir: str | None = None

    # ------------------------------------------------------------------
    # Read-only state
    # ------------------------------------------------------------------

    @property
    def state(self) -> DictateState:
        return self._state

    @property
    def is_recording(self) -> bool:
        return self._state == DictateState.RECORDING

    @property
    def is_toggle_recording(self) -> bool:
        """True only when recording was started via double-tap (toggle mode)."""
        return self._state == DictateState.RECORDING and not self._is_hold_mode

    def get_ui_state(self) -> str:
        """Return 'recording' | 'processing' | 'idle' for panel UI."""
        if self._state == DictateState.RECORDING:
            return "recording"
        if self._state == DictateState.TRANSCRIBING:
            return "processing"
        return "idle"

    # ------------------------------------------------------------------
    # Hotkey entry points
    # ------------------------------------------------------------------

    def handle_toggle(self) -> dict:
        """Called on double-tap of the dictate key.

        IDLE → start recording (toggle mode).
        RECORDING (toggle mode) → stop and paste in background.
        RECORDING (hold mode) → no-op (stop is handled by handle_hold_end).
        """
        with self._lock:
            if self._state == DictateState.IDLE:
                return self._start_recording(hold=False)
            if self._state == DictateState.RECORDING and not self._is_hold_mode:
                return self._stop_and_paste_async()
            return {"ok": True}

    def handle_hold_start(self) -> dict:
        """Called when the dictate key is held past the hold threshold.

        IDLE → start recording (hold mode).
        RECORDING → no-op (already started, hold_end will stop it).
        """
        with self._lock:
            if self._state == DictateState.IDLE:
                return self._start_recording(hold=True)
            return {"ok": True}

    def handle_hold_end(self) -> dict:
        """Called when the held dictate key is released.

        RECORDING (hold mode) → stop and paste in background.
        Any other state → no-op.
        """
        with self._lock:
            if self._state == DictateState.RECORDING and self._is_hold_mode:
                return self._stop_and_paste_async()
            return {"ok": True}

    def handle_cancel(self) -> dict:
        """Cancel an in-progress recording without transcribing or pasting.

        RECORDING → stop audio, discard, call on_paste_complete (to hide overlay).
        Any other state → no-op (too late to cancel if worker is already running).
        """
        with self._lock:
            if self._state == DictateState.RECORDING:
                self._state = DictateState.TRANSCRIBING
                self._is_hold_mode = False
                self._start_time = None
                worker = threading.Thread(
                    target=self._stop_audio_no_paste, daemon=True, name="dictate-cancel"
                )
                worker.start()
                return {"ok": True, "cancelled": True}
        return {"ok": True, "cancelled": False}

    # ------------------------------------------------------------------
    # Internal start / stop (called under _lock)
    # ------------------------------------------------------------------

    def _start_recording(self, hold: bool) -> dict:
        """Validate permissions + model, then start the audio session."""
        ok, missing = self._can_dictate()
        if not ok:
            return {
                "ok": False,
                "error": ERROR_SETUP_REQUIRED,
                "missing_permissions": missing,
            }

        model = self._config.dictation_model
        if not self._model.is_downloaded(model):
            return {"ok": False, "error": ERROR_NO_MODEL, "model": model}

        self._target_bundle_id = _get_frontmost_bundle_id()

        self._dictate_temp_dir = tempfile.mkdtemp(prefix="liscribe_dictate_")
        try:
            self._audio.start(
                mic=self._config.default_mic,
                speaker=False,
                save_folder_override=self._dictate_temp_dir,
            )
        except Exception as exc:
            shutil.rmtree(self._dictate_temp_dir, ignore_errors=True)
            self._dictate_temp_dir = None
            logger.error("DictateController: audio start failed: %s", exc)
            return {"ok": False, "error": str(exc)}

        self._state = DictateState.RECORDING
        self._is_hold_mode = hold
        self._start_time = time.monotonic()
        return {"ok": True}

    def _stop_and_paste_async(self) -> dict:
        """Transition state to TRANSCRIBING and launch the stop+transcribe+paste thread."""
        self._state = DictateState.TRANSCRIBING
        self._is_hold_mode = False
        recording_start = self._start_time
        self._start_time = None

        worker = threading.Thread(
            target=self._stop_transcribe_paste,
            args=(recording_start,),
            daemon=True,
            name="dictate-worker",
        )
        self._last_worker = worker
        worker.start()
        return {"ok": True}

    def _stop_audio_no_paste(self) -> None:
        """Stop audio and discard — no transcription, no paste. Runs in a daemon thread."""
        try:
            self._audio.stop()
        except Exception:
            logger.debug("DictateController: cancel audio stop failed", exc_info=True)
        finally:
            self._state = DictateState.IDLE
            if self._dictate_temp_dir:
                shutil.rmtree(self._dictate_temp_dir, ignore_errors=True)
                self._dictate_temp_dir = None
            if self._on_paste_complete:
                self._on_paste_complete()

    def _do_paste_on_main(self, target: str | None, text: str) -> None:
        """Run on main thread: clipboard, optionally activate target app, always paste, optional Enter, notify, on_paste_complete."""
        try:
            import pyperclip

            pyperclip.copy(text)
        except Exception as exc:
            logger.error("DictateController: clipboard copy failed: %s", exc)
            if self._on_paste_complete:
                self._on_paste_complete()
            return
        # Activate target app first only when we have one; paste always runs (into that app or current frontmost).
        if target:
            try:
                _activate_bundle(target)
            except Exception as exc:
                logger.warning("DictateController: activate bundle failed: %s", exc)
        try:
            _simulate_paste()
        except Exception as exc:
            logger.warning("DictateController: simulate paste failed: %s", exc)
            _notify("Dictated text copied to clipboard", text[:80])
            if self._on_paste_complete:
                self._on_paste_complete()
            return
        # Enter only when the setting is on (and we had a target to paste into).
        if target and self._config.dictation_auto_enter:
            try:
                time.sleep(0.12)
                _simulate_enter()
            except Exception as exc:
                logger.debug("DictateController: simulate enter failed: %s", exc)
        if self._on_paste_complete:
            self._on_paste_complete()

    def _notify_transcription_failed_on_main(self, exc: Exception) -> None:
        """Run on main thread: notify user and call on_paste_complete."""
        _notify("Dictate failed", f"Transcription error: {exc}")
        if self._on_paste_complete:
            self._on_paste_complete()

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _stop_transcribe_paste(self, recording_start: float | None = None) -> None:
        """Stop recording, transcribe, and paste. Runs in a daemon thread."""
        try:
            wav_path = self._audio.stop()
            if not wav_path:
                logger.warning("DictateController: no WAV path after stop — nothing to transcribe")
                return

            model = self._config.dictation_model
            try:
                result = self._model.transcribe(wav_path, model_size=model)
                text = result.text.strip() if result.text else ""
            except Exception as exc:
                logger.error("DictateController: transcription failed: %s", exc)
                if self._run_on_main:
                    self._run_on_main(lambda _e=exc: self._notify_transcription_failed_on_main(_e))
                else:
                    _notify("Dictate failed", f"Transcription error: {exc}")
                return

            if not text:
                logger.debug("DictateController: empty transcription result, nothing to paste")
                if self._on_paste_complete:
                    self._on_paste_complete()
                return

            t0 = time.perf_counter()
            before_len = len(text)
            text = _replacements.apply(
                text,
                self._config.replacement_rules,
                "dictate",
            )

            webhook_url = self._config.webhook_url
            if webhook_url and self._config.webhook_auto_send_dictate:
                _post_webhook_dictate(
                    webhook_url,
                    text=text,
                    recording_start=recording_start,
                    auth_header_name=self._config.webhook_auth_header_name,
                    auth_header_value=self._config.webhook_auth_header_value,
                )

            target = self._target_bundle_id
            if self._run_on_main:
                # AppKit, rumps, and pynput must run on main thread on macOS.
                self._run_on_main(lambda: self._do_paste_on_main(target, text))
            else:
                try:
                    import pyperclip

                    pyperclip.copy(text)
                except Exception as exc:
                    logger.error("DictateController: clipboard copy failed: %s", exc)
                    return

                if target:
                    try:
                        _activate_bundle(target)
                        _simulate_paste()
                        if self._config.dictation_auto_enter:
                            time.sleep(0.12)  # let target app apply paste before Enter
                            _simulate_enter()
                    except Exception as exc:
                        logger.warning("DictateController: keyboard paste failed: %s", exc)
                        _notify("Dictated text copied to clipboard", text[:80])
                else:
                    _notify("Dictated text copied to clipboard", text[:80])
        finally:
            self._state = DictateState.IDLE
            if self._dictate_temp_dir:
                shutil.rmtree(self._dictate_temp_dir, ignore_errors=True)
                self._dictate_temp_dir = None
            if self._on_paste_complete and not self._run_on_main:
                self._on_paste_complete()

    # ------------------------------------------------------------------
    # Real-time data (for bridge polling)
    # ------------------------------------------------------------------

    def get_waveform(self, bars: int = 30) -> list[float]:
        """Return current audio level bars (0.0–1.0) for waveform display."""
        return self._audio.get_levels(bars=bars)

    def get_elapsed(self) -> float:
        """Return seconds elapsed since recording started, or 0.0 when idle."""
        if self._state != DictateState.RECORDING or self._start_time is None:
            return 0.0
        return time.monotonic() - self._start_time
