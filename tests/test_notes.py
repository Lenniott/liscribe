"""Tests for notes module."""

import time
from liscribe.notes import NoteCollection


class TestNoteCollection:
    def test_add_and_retrieve(self):
        nc = NoteCollection()
        nc.start()
        nc.add("First note")
        nc.add("Second note")
        assert len(nc.notes) == 2
        assert nc.texts == ["First note", "Second note"]

    def test_indexes_start_at_one(self):
        nc = NoteCollection()
        nc.start()
        n1 = nc.add("A")
        n2 = nc.add("B")
        assert n1.index == 1
        assert n2.index == 2

    def test_footnotes_rendering(self):
        nc = NoteCollection()
        nc.start()
        nc.add("Check budget")
        nc.add("Email Sarah")
        text = nc.as_footnotes()
        assert "[^1]: Check budget" in text
        assert "[^2]: Email Sarah" in text

    def test_footnotes_without_time(self):
        nc = NoteCollection()
        nc.start()
        nc.add("Check budget")
        text = nc.as_footnotes(include_time=False)
        assert "[^1]: Check budget" in text
        assert "(at " not in text

    def test_start_from_external_time(self):
        nc = NoteCollection()
        base = time.time() - 10.0
        nc.start_from(base)
        note = nc.add("Late note")
        assert note.timestamp >= 10.0

    def test_clear(self):
        nc = NoteCollection()
        nc.start()
        nc.add("Note")
        nc.clear()
        assert len(nc.notes) == 0

    def test_empty_footnotes(self):
        nc = NoteCollection()
        assert nc.as_footnotes() == ""
