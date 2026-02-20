"""Audio recording core — mic listing, selection, recording, mid-session mic switching.

Design:
- Mic-only mode saves one WAV file.
- Recording runs via sounddevice callbacks appending chunks to lists.
- Mid-recording mic switch: stop current InputStream, start new one on the
  new device, continue appending to the same chunk list. Short gap (~50ms)
  is acceptable and preferable to data corruption.
- Speaker capture (-s): open a second InputStream from BlackHole and save
  mic/system audio as separate files with shared session metadata.
"""

from __future__ import annotations

import atexit
import json
import logging
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import sounddevice as sd
from scipy.io import wavfile

from liscribe.config import load_config
from liscribe.platform_setup import (
    get_current_output_device,
    set_output_device,
)

logger = logging.getLogger(__name__)


def _extract_input_adc_time(time_info: Any) -> float | None:
    """Best-effort extraction of input ADC time from sounddevice callback metadata."""
    for key in ("inputBufferAdcTime", "input_buffer_adc_time"):
        try:
            value = getattr(time_info, key)
            if value is not None:
                return float(value)
        except Exception:
            pass
    if isinstance(time_info, dict):
        for key in ("inputBufferAdcTime", "input_buffer_adc_time"):
            value = time_info.get(key)
            if value is not None:
                try:
                    return float(value)
                except Exception:
                    return None
    return None


def _to_int16(audio_data: np.ndarray) -> np.ndarray:
    """Convert float32/float64 audio in [-1,1] to int16 safely."""
    return np.clip(audio_data * 32767, -32768, 32767).astype(np.int16)


def _save_private_wav(path: Path, sample_rate: int, audio_data: np.ndarray) -> None:
    """Write WAV and force user-only read/write permissions."""
    wavfile.write(str(path), sample_rate, _to_int16(audio_data))
    path.chmod(0o600)


def list_input_devices() -> list[dict[str, Any]]:
    """Return a list of available input devices with their properties."""
    devices = sd.query_devices()
    result = []
    default_input = sd.default.device[0]
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0:
            result.append({
                "index": i,
                "name": d["name"],
                "channels": d["max_input_channels"],
                "sample_rate": int(d["default_samplerate"]),
                "is_default": i == default_input,
            })
    return result


def resolve_device(mic: str | None) -> int | None:
    """Resolve a mic argument (name or index string) to a device index.

    Returns None for system default.
    """
    if mic is None:
        return None

    try:
        idx = int(mic)
        devs = sd.query_devices()
        if 0 <= idx < len(devs) and devs[idx]["max_input_channels"] > 0:
            return idx
        raise ValueError(f"Device index {idx} is not a valid input device.")
    except ValueError:
        pass

    mic_lower = mic.lower()
    for dev in list_input_devices():
        if mic_lower in dev["name"].lower():
            return dev["index"]

    raise ValueError(f"No input device matching '{mic}' found.")


def _find_blackhole_device(name_hint: str = "BlackHole 2ch") -> int | None:
    """Find the BlackHole input device index."""
    hint_lower = name_hint.lower()
    for dev in list_input_devices():
        if hint_lower in dev["name"].lower():
            return dev["index"]
    return None


class RecordingSession:
    """Manages a single recording session with optional dual-stream (mic + speaker)."""

    def __init__(
        self,
        folder: str,
        speaker: bool = False,
        mic: str | None = None,
    ):
        cfg = load_config()
        self.sample_rate: int = cfg.get("sample_rate", 16000)
        self.channels: int = cfg.get("channels", 1)
        self.speaker_device_name: str = cfg.get("speaker_device", "Multi-Output Device")
        self.blackhole_name: str = cfg.get("blackhole_device", "BlackHole 2ch")

        self.save_dir = Path(folder).expanduser().resolve()
        self.save_dir.mkdir(parents=True, exist_ok=True)

        self.speaker = speaker
        self.mic_arg = mic
        self.device_idx: int | None = None
        self.blackhole_idx: int | None = None

        self._mic_chunks: list[np.ndarray] = []
        self._speaker_chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._mic_stream: sd.InputStream | None = None
        self._speaker_stream: sd.InputStream | None = None
        self._stop_requested = threading.Event()
        self._original_output: str | None = None
        self._start_time: float = 0.0
        self._mic_device_name: str = "unknown"
        self._speaker_enabled_ever: bool = speaker
        self._mic_first_adc_time: float | None = None
        self._speaker_first_adc_time: float | None = None

    def _mic_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        if status:
            logger.warning("Mic callback status: %s", status)
        adc_time = _extract_input_adc_time(time_info)
        with self._lock:
            if self._mic_first_adc_time is None and adc_time is not None:
                self._mic_first_adc_time = adc_time
            self._mic_chunks.append(indata.copy())

    def _speaker_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        if status:
            logger.warning("Speaker callback status: %s", status)
        adc_time = _extract_input_adc_time(time_info)
        with self._lock:
            if self._speaker_first_adc_time is None and adc_time is not None:
                self._speaker_first_adc_time = adc_time
            self._speaker_chunks.append(indata.copy())

    def _open_mic_stream(self, device: int | None) -> sd.InputStream:
        stream = sd.InputStream(
            device=device,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._mic_callback,
            blocksize=1024,
        )
        stream.start()
        return stream

    def _open_speaker_stream(self, device: int) -> sd.InputStream:
        stream = sd.InputStream(
            device=device,
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._speaker_callback,
            blocksize=1024,
        )
        stream.start()
        return stream

    def switch_mic(self, new_device: int | None) -> None:
        """Switch the active mic mid-recording."""
        logger.info("Switching mic to device %s", new_device)

        if self._mic_stream is not None:
            self._mic_stream.stop()
            self._mic_stream.close()

        self._mic_stream = self._open_mic_stream(new_device)
        self.device_idx = new_device

        if new_device is not None:
            dev_info = sd.query_devices(new_device)
            logger.info("Mic switched to: %s", dev_info["name"])

    def _restore_audio_output(self) -> None:
        """Restore original audio output device if we changed it."""
        if self._original_output is not None:
            set_output_device(self._original_output)
            logger.info("Restored audio output to: %s", self._original_output)
            self._original_output = None

    def enable_speaker_capture(self) -> str | None:
        """Enable speaker capture mid-recording. Returns None on success, error message on failure."""
        if self.speaker:
            return None
        self.blackhole_idx = _find_blackhole_device(self.blackhole_name)
        if self.blackhole_idx is None:
            return f"BlackHole '{self.blackhole_name}' not found. Run setup for instructions."
        self._original_output = get_current_output_device()
        if not set_output_device(self.speaker_device_name):
            return (
                f"Could not switch to '{self.speaker_device_name}'. "
                "Create a Multi-Output Device in Audio MIDI Setup (see setup)."
            )
        atexit.register(self._restore_audio_output)
        try:
            self._speaker_stream = self._open_speaker_stream(self.blackhole_idx)
        except sd.PortAudioError as exc:
            self._restore_audio_output()
            return f"Error starting speaker capture: {exc}"
        self.speaker = True
        self._speaker_enabled_ever = True
        return None

    def disable_speaker_capture(self) -> None:
        """Disable speaker capture mid-recording and restore output routing."""
        if self._speaker_stream is not None:
            self._speaker_stream.stop()
            self._speaker_stream.close()
            self._speaker_stream = None
        self._restore_audio_output()
        self.speaker = False

    def start(self) -> str | None:
        """Run the recording session. Returns path to saved WAV or None on cancel."""
        # Resolve mic
        try:
            self.device_idx = resolve_device(self.mic_arg)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return None

        # Speaker setup
        if self.speaker:
            self.blackhole_idx = _find_blackhole_device(self.blackhole_name)
            if self.blackhole_idx is None:
                cmd_name = load_config().get("command_alias", "rec")
                print(
                    f"Error: BlackHole device '{self.blackhole_name}' not found.\n"
                    f"Run '{cmd_name} setup' for install instructions.",
                    file=sys.stderr,
                )
                return None

            self._original_output = get_current_output_device()
            if not set_output_device(self.speaker_device_name):
                cmd_name = load_config().get("command_alias", "rec")
                print(
                    f"Error: Could not switch output to '{self.speaker_device_name}'.\n"
                    "Make sure you've created a Multi-Output Device in Audio MIDI Setup\n"
                    "that includes your speakers AND BlackHole 2ch.\n"
                    f"Run '{cmd_name} setup' for instructions.",
                    file=sys.stderr,
                )
                return None

            # Register cleanup so we restore output even on crash
            atexit.register(self._restore_audio_output)

        # Device display name
        if self.device_idx is not None:
            dev_info = sd.query_devices(self.device_idx)
            self._mic_device_name = str(dev_info["name"])
        else:
            dev_info = sd.query_devices(sd.default.device[0])
            self._mic_device_name = str(dev_info["name"])

        dev_name = self._mic_device_name if self.device_idx is not None else f"{self._mic_device_name} (default)"

        # Start streams
        try:
            self._mic_stream = self._open_mic_stream(self.device_idx)
            if self.speaker and self.blackhole_idx is not None:
                self._speaker_stream = self._open_speaker_stream(self.blackhole_idx)
        except sd.PortAudioError as exc:
            print(f"Error starting recording: {exc}", file=sys.stderr)
            self._restore_audio_output()
            return None

        self._start_time = time.time()
        mode = "mic + speaker" if self.speaker else "mic"
        print(f"Recording ({mode})... Mic: {dev_name} | {self.sample_rate}Hz {self.channels}ch")
        if self.speaker:
            print(f"Speaker capture via: {self.blackhole_name}")
        print("Press Ctrl+C to stop and save.\n")

        # Handle Ctrl+C
        original_sigint = signal.getsignal(signal.SIGINT)

        def _handle_sigint(signum: int, frame: Any) -> None:
            self._stop_requested.set()

        signal.signal(signal.SIGINT, _handle_sigint)

        try:
            while not self._stop_requested.is_set():
                elapsed = time.time() - self._start_time
                mins, secs = divmod(int(elapsed), 60)
                hrs, mins = divmod(mins, 60)
                print(f"\r  ● REC  {hrs:02d}:{mins:02d}:{secs:02d}", end="", flush=True)
                time.sleep(0.5)
        finally:
            signal.signal(signal.SIGINT, original_sigint)

        return self._stop_and_save()

    def _stop_and_save(self) -> str | None:
        """Stop streams and save recording artifacts."""
        print()

        # Stop streams
        for stream in (self._mic_stream, self._speaker_stream):
            if stream is not None:
                stream.stop()
                stream.close()
        self._mic_stream = None
        self._speaker_stream = None

        # Restore audio output
        self._restore_audio_output()

        elapsed = time.time() - self._start_time

        dual_source_mode = self._speaker_enabled_ever

        with self._lock:
            if not self._mic_chunks:
                print("No audio recorded.")
                return None

            mic_audio = np.concatenate(self._mic_chunks, axis=0)
            self._mic_chunks.clear()

            if self._speaker_chunks:
                speaker_audio = np.concatenate(self._speaker_chunks, axis=0).astype(np.float32)
            else:
                speaker_audio = np.empty((0, self.channels), dtype=np.float32) if self.channels > 1 else np.empty(0, dtype=np.float32)
            self._speaker_chunks.clear()

            mic_audio = mic_audio.astype(np.float32)

        # Generate filename and save
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        if not dual_source_mode:
            wav_path = self.save_dir / f"{timestamp}.wav"
            _save_private_wav(wav_path, self.sample_rate, mic_audio)
            mins, secs = divmod(int(elapsed), 60)
            print(f"Saved: {wav_path} ({mins}m {secs}s)")
            return str(wav_path)

        session_dir = self.save_dir / timestamp
        session_dir.mkdir(parents=True, exist_ok=True)

        mic_len = len(mic_audio)
        spk_len = len(speaker_audio)
        if spk_len < mic_len:
            pad_spec = ((0, mic_len - spk_len), (0, 0)) if speaker_audio.ndim == 2 else (0, mic_len - spk_len)
            speaker_audio = np.pad(speaker_audio, pad_spec)
        elif spk_len > mic_len:
            pad_spec = ((0, spk_len - mic_len), (0, 0)) if mic_audio.ndim == 2 else (0, spk_len - mic_len)
            mic_audio = np.pad(mic_audio, pad_spec)

        mic_wav = session_dir / "mic.wav"
        speaker_wav = session_dir / "speaker.wav"
        _save_private_wav(mic_wav, self.sample_rate, mic_audio)
        _save_private_wav(speaker_wav, self.sample_rate, speaker_audio.astype(np.float32))

        offset = 0.0
        if self._mic_first_adc_time is not None and self._speaker_first_adc_time is not None:
            offset = round(self._speaker_first_adc_time - self._mic_first_adc_time, 4)

        start_unix = float(self._start_time or time.time())
        metadata = {
            "mode": "mic+speaker",
            "t0_unix": start_unix,
            "t0_iso": datetime.fromtimestamp(start_unix).isoformat(),
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "devices": {
                "mic": self._mic_device_name,
                "speaker_input": self.blackhole_name,
                "speaker_output_device": self.speaker_device_name,
            },
            "offset_correction_seconds": offset,
        }
        session_meta_path = session_dir / "session.json"
        session_meta_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        session_meta_path.chmod(0o600)

        mins, secs = divmod(int(elapsed), 60)
        print(f"Saved: {session_dir} ({mins}m {secs}s)")
        return str(mic_wav)


def start_recording_session(
    folder: str,
    speaker: bool = False,
    mic: str | None = None,
) -> str | None:
    """Start a recording session. Returns path to saved WAV or None."""
    session = RecordingSession(folder=folder, speaker=speaker, mic=mic)
    return session.start()
