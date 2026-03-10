"""Scribe panel bridge.

Translates JS calls from scribe.html into Python controller/service calls.
No business logic lives here — this is a translation layer only.

pywebview exposes every public method of the bridge object as a JS-callable
function on the ``window.pywebview.api`` namespace.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from liscribe.path_display import from_display, to_display

if TYPE_CHECKING:
    from liscribe.controllers.scribe_controller import ScribeController
    from liscribe.services.audio_service import AudioService
    from liscribe.services.model_service import ModelService

logger = logging.getLogger(__name__)


class ScribeAppActions(Protocol):
    """App-level actions the Scribe panel can trigger. One object replaces four optional callbacks."""

    def close_panel(self) -> None: ...
    def request_close(self) -> None: ...
    def transcription_finished(self) -> None: ...
    def open_in_transcribe(self, wav_path: str, save_folder: str | None) -> None: ...


def _invoke(
    name: str,
    app_actions: ScribeAppActions | None,
    method: str,
) -> None:
    """Call app_actions.method() if wired; otherwise log. Reduces callback boilerplate."""
    if app_actions is not None:
        getattr(app_actions, method)()
    else:
        logger.info("%s requested (no app_actions wired)", name)


class ScribeBridge:
    """JS-callable API for the Scribe panel.

    Receives controller and services as constructor arguments.
    Instantiated once in app.py and registered with the scribe window.
    """

    def __init__(
        self,
        controller: ScribeController,
        model: ModelService,
        audio: AudioService,
        app_actions: ScribeAppActions | None = None,
    ) -> None:
        self._controller = controller
        self._model = model
        self._audio = audio
        self._app_actions = app_actions

    # ------------------------------------------------------------------
    # Device / model queries
    # ------------------------------------------------------------------

    def get_mics(self) -> list[dict]:
        """Return available microphones, each annotated with fallback status.

        On any exception (e.g. permission, sounddevice init), logs and returns []
        so the UI shows "no mics" instead of breaking. Callers cannot distinguish
        "no devices" from "error"; see logs for debugging.
        """
        try:
            mics = self._audio.list_mics()
        except Exception as e:
            logger.warning("list_mics failed (returning empty list): %s", e, exc_info=True)
            mics = []
        is_fallback = self._controller.is_using_fallback_mic
        return [
            {**mic, "is_fallback_active": is_fallback}
            for mic in mics
        ]

    def get_models(self) -> list[dict]:
        """Return all models with download status and selection flag."""
        selected = set(self._controller.selected_models)
        return [
            {**m, "is_selected": m["name"] in selected}
            for m in self._model.list_models()
        ]

    def get_save_path(self) -> str:
        """Return save path in display form (~ for home)."""
        return to_display(self._controller.save_path)

    def open_transcript(self, file_path: str) -> None:
        """Open the transcript file with the app set in Settings (same as Transcribe panel)."""
        self._controller.open_transcript(from_display(file_path))

    # ------------------------------------------------------------------
    # Session configuration
    # ------------------------------------------------------------------

    def set_save_path(self, path: str) -> None:
        """Accept display path (~); expand before passing to controller."""
        self._controller.set_save_path(from_display(path or ""))

    def set_mic(self, name: str | None) -> None:
        """Set the active mic. Switches mid-recording if already recording."""
        self._controller.set_mic(name)
        if self._controller.is_recording:
            self._controller.switch_mic(name)

    def toggle_speaker(self, enabled: bool) -> dict:
        """Enable or disable speaker capture.

        Returns ``{"ok": True}`` on success, or ``{"ok": False, "error": "…"}``
        if the audio layer could not apply the change (e.g. BlackHole absent).
        """
        error = self._controller.set_speaker(enabled)
        if error:
            return {"ok": False, "error": error}
        return {"ok": True}

    def toggle_model(self, name: str, selected: bool) -> None:
        """Add or remove a model from the session selection."""
        current = list(self._controller.selected_models)
        if selected and name not in current:
            current.append(name)
        elif not selected and name in current:
            current.remove(name)
        self._controller.set_models(current)

    # ------------------------------------------------------------------
    # Recording controls
    # ------------------------------------------------------------------

    def stop_and_save(self) -> dict:
        """Stop recording and begin transcription.

        Returns the initial result state immediately. JS should then poll
        get_transcription_progress() until all models are done.
        """
        try:
            result = self._controller.stop_and_save()
            return {
                "ok": True,
                "is_no_model_mode": result.is_no_model_mode,
                "wav_path": to_display(result.wav_path),
                "save_folder": to_display(result.save_folder),
                "transcripts": [
                    {
                        "model_name": t.model_name,
                        "progress": t.progress,
                        "md_path": to_display(t.md_path) if t.md_path else t.md_path,
                        "error": t.error,
                        "is_done": t.is_done,
                    }
                    for t in result.transcripts
                ],
            }
        except RuntimeError as exc:
            logger.error("stop_and_save failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    def cancel(self) -> dict:
        """Discard the current recording."""
        self._controller.cancel()
        return {"ok": True}

    # ------------------------------------------------------------------
    # Real-time data (JS polls these)
    # ------------------------------------------------------------------

    def get_waveform(self, bars: int = 30) -> list[float]:
        """Return audio level bars for waveform display. Optional bars (default 30) matches frontend bar count."""
        return self._controller.get_waveform(bars)

    def get_elapsed(self) -> float:
        return self._controller.get_elapsed_seconds()

    def get_transcription_progress(self) -> list[dict]:
        """Return progress with paths in display form (~ for home)."""
        raw = self._controller.get_transcription_progress()
        wav_path = to_display(self._controller.wav_path)
        return [
            {
                **p,
                "md_path": to_display(p.get("md_path")) if p.get("md_path") else p.get("md_path"),
                "wav_path": wav_path,
            }
            for p in raw
        ]

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------

    def add_note(self, text: str) -> dict:
        """Add a timestamped note to the current recording.

        Returns ``{"ok": True, "index": N}`` on success, or
        ``{"ok": False, "error": "…"}`` if not currently recording.
        """
        try:
            note = self._controller.add_note(text)
            return {"ok": True, "index": note.index, "timestamp": note.timestamp}
        except RuntimeError as exc:
            logger.warning("add_note failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Panel state snapshot (called on panel load and after state changes)
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """Return a full snapshot of the current panel state for JS rendering.
        Paths in display form (~ for home).
        """
        return {
            "state": self._controller.state.value,
            "is_using_fallback_mic": self._controller.is_using_fallback_mic,
            "save_path": to_display(self._controller.save_path),
            "selected_models": self._controller.selected_models,
            "current_mic": self._controller.current_mic,
        }

    # ------------------------------------------------------------------
    # Cross-panel navigation
    # ------------------------------------------------------------------

    def open_in_transcribe(self, wav_path: str, save_folder: str | None = None) -> None:
        """Signal the app to open the Transcribe panel with wav_path (and optional save_folder) pre-filled."""
        if self._app_actions is not None:
            self._app_actions.open_in_transcribe(wav_path, save_folder or None)
        else:
            logger.info("open_in_transcribe requested for %s (no app_actions wired)", wav_path)

    def close_panel(self) -> None:
        """Close the Scribe panel (e.g. after Leave and discard)."""
        _invoke("close_panel", self._app_actions, "close_panel")

    def request_close(self) -> None:
        """Request to close the panel (triggers the same native confirm dialog as the red X)."""
        _invoke("request_close", self._app_actions, "request_close")

    def transcription_finished(self) -> None:
        """Called when all transcription is done; disables the close warning so the red X just closes."""
        _invoke("transcription_finished", self._app_actions, "transcription_finished")
