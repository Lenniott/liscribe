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
        """Return current level history as list of 0.0–1.0 values."""
        with self._lock:
            if not self._history:
                return []
            peak = self._peak if self._peak > 0 else 1.0
            return [min(v / peak, 1.0) for v in self._history]

    def render(self) -> str:
        """Render the waveform as a string of Unicode block characters."""
        levels = self.get_levels()
        if not levels:
            return " " * BAR_WIDTH
        chars = []
        for level in levels:
            idx = int(level * (len(BLOCKS) - 1))
            chars.append(BLOCKS[idx])
        # Pad to full width
        while len(chars) < BAR_WIDTH:
            chars.insert(0, " ")
        return "".join(chars[-BAR_WIDTH:])

    def get_current_rms(self) -> float:
        """Return the most recent RMS value."""
        with self._lock:
            return self._history[-1] if self._history else 0.0

    def reset(self) -> None:
        """Clear history."""
        with self._lock:
            self._history.clear()
            self._peak = 0.0
