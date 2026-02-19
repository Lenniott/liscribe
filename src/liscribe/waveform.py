"""Real-time audio level waveform display for the TUI.

Converts audio RMS levels to Unicode block characters for a visual
representation of audio input.
"""

from __future__ import annotations

import threading
from collections import deque

import numpy as np

BLOCKS = " ▁▂▃▄▅▆▇█"
BAR_WIDTH = 60


class WaveformMonitor:
    """Thread-safe audio level monitor that tracks RMS history."""

    def __init__(self, max_history: int = BAR_WIDTH):
        self._history: deque[float] = deque(maxlen=max_history)
        self._lock = threading.Lock()
        self._peak: float = 0.0

    def push(self, audio_chunk: np.ndarray) -> None:
        """Process an audio chunk and add its RMS level to history."""
        if audio_chunk.size == 0:
            return
        rms = float(np.sqrt(np.mean(audio_chunk.astype(np.float64) ** 2)))
        with self._lock:
            self._history.append(rms)
            self._peak = max(self._peak, rms)

    def get_levels(self) -> list[float]:
        """Return current level history as list of 0.0–1.0 values.
        Uses a decaying peak so the scale doesn't get stuck after loud moments.
        """
        with self._lock:
            if not self._history:
                return []
            current_max = max(self._history)
            # Decay peak slowly so display recovers after loud spikes
            peak = max(self._peak * 0.997, current_max, 1e-6)
            self._peak = peak
            return [min(v / peak, 1.0) for v in self._history]

    def render(self, width: int | None = None) -> str:
        """Render the waveform as a string of Unicode block characters.
        If width is given, use that many characters (responsive to terminal width).
        """
        w = width if width is not None and width > 0 else BAR_WIDTH
        levels = self.get_levels()
        if not levels:
            return " " * w
        # Sample or pad levels to match width
        if len(levels) >= w:
            step = len(levels) / w
            levels = [levels[int(i * step)] for i in range(w)]
        else:
            levels = ([0.0] * (w - len(levels))) + levels
        chars = []
        for level in levels:
            idx = int(level * (len(BLOCKS) - 1))
            chars.append(BLOCKS[idx])
        return "".join(chars[:w])

    def get_current_rms(self) -> float:
        """Return the most recent RMS value."""
        with self._lock:
            return self._history[-1] if self._history else 0.0

    def reset(self) -> None:
        """Clear history."""
        with self._lock:
            self._history.clear()
            self._peak = 0.0
