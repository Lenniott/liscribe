"""Note capture and transcript linking.

Notes taken during recording are timestamped and later appended to the
transcript as Markdown footnotes: [1], [2], ... in-text become
[^1]: note text, [^2]: note text at the end.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class Note:
    index: int
    text: str
    timestamp: float  # seconds since recording start


@dataclass
class NoteCollection:
    """Collects timestamped notes during a recording session."""

    _notes: list[Note] = field(default_factory=list)
    _start_time: float = 0.0

    def start(self) -> None:
        self._start_time = time.time()

    def add(self, text: str) -> Note:
        idx = len(self._notes) + 1
        elapsed = time.time() - self._start_time if self._start_time else 0.0
        note = Note(index=idx, text=text, timestamp=elapsed)
        self._notes.append(note)
        return note

    @property
    def notes(self) -> list[Note]:
        return list(self._notes)

    @property
    def texts(self) -> list[str]:
        return [n.text for n in self._notes]

    def as_footnotes(self) -> str:
        """Render all notes as Markdown footnotes."""
        if not self._notes:
            return ""
        lines = []
        for note in self._notes:
            mins, secs = divmod(int(note.timestamp), 60)
            lines.append(f"[^{note.index}]: {note.text} (at {mins}:{secs:02d})")
        return "\n".join(lines)

    def clear(self) -> None:
        self._notes.clear()
        self._start_time = 0.0
