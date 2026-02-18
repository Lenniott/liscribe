"""Audio recording core — mic listing, selection, recording, mid-session mic switching.

Design:
- One WAV file per session, saved to the folder given by -f.
- Recording runs via sounddevice callbacks appending chunks to lists.
- Mid-recording mic switch: stop current InputStream, start new one on the
  new device, continue appending to the same chunk list. Short gap (~50ms)
  is acceptable and preferable to data corruption.
- Speaker capture (-s): open a second InputStream from BlackHole, mix both
  streams into one WAV on save.
- On stop: concatenate all chunks (and mix if dual-stream) and write a single WAV.
"""

from __future__ import annotations

import atexit
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

    def _mic_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        if status:
            logger.warning("Mic callback status: %s", status)
        with self._lock:
            self._mic_chunks.append(indata.copy())

    def _speaker_callback(self, indata: np.ndarray, frames: int, time_info: Any, status: sd.CallbackFlags) -> None:
        if status:
            logger.warning("Speaker callback status: %s", status)
        with self._lock:
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
        return None

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
            dev_name = dev_info["name"]
        else:
            dev_info = sd.query_devices(sd.default.device[0])
            dev_name = f"{dev_info['name']} (default)"

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
        """Stop streams, mix audio, save WAV, restore output."""
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

        with self._lock:
            if not self._mic_chunks:
                print("No audio recorded.")
                return None

            mic_audio = np.concatenate(self._mic_chunks, axis=0)
            self._mic_chunks.clear()

            if self.speaker and self._speaker_chunks:
                speaker_audio = np.concatenate(self._speaker_chunks, axis=0)
                self._speaker_chunks.clear()

                # Align lengths: pad shorter with zeros
                mic_len = len(mic_audio)
                spk_len = len(speaker_audio)
                if mic_len > spk_len:
                    speaker_audio = np.pad(speaker_audio, ((0, mic_len - spk_len), (0, 0)) if speaker_audio.ndim == 2 else (0, mic_len - spk_len))
                elif spk_len > mic_len:
                    mic_audio = np.pad(mic_audio, ((0, spk_len - mic_len), (0, 0)) if mic_audio.ndim == 2 else (0, spk_len - mic_len))

                # Mix: average the two signals
                mixed = (mic_audio.astype(np.float64) + speaker_audio.astype(np.float64)) / 2.0
                audio_data = mixed.astype(np.float32)
            else:
                audio_data = mic_audio

        # Generate filename and save
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        wav_path = self.save_dir / f"{timestamp}.wav"

        audio_int16 = np.clip(audio_data * 32767, -32768, 32767).astype(np.int16)
        wavfile.write(str(wav_path), self.sample_rate, audio_int16)

        mins, secs = divmod(int(elapsed), 60)
        print(f"Saved: {wav_path} ({mins}m {secs}s)")
        return str(wav_path)


def start_recording_session(
    folder: str,
    speaker: bool = False,
    mic: str | None = None,
) -> str | None:
    """Start a recording session. Returns path to saved WAV or None."""
    session = RecordingSession(folder=folder, speaker=speaker, mic=mic)
    return session.start()
