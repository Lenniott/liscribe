"""Tests for output module."""

import tempfile
from pathlib import Path

from liscribe.transcriber import TranscriptionResult
from liscribe.output import build_markdown, save_transcript, cleanup_audio


def _make_result(text: str = "Hello world.") -> TranscriptionResult:
    return TranscriptionResult(
        text=text,
        segments=[{"start": 0.0, "end": 1.0, "text": text}],
        language="en",
        duration=2.0,
    )


class TestBuildMarkdown:
    def test_contains_front_matter(self):
        md = build_markdown(_make_result(), "/tmp/test.wav")
        assert md.startswith("---")
        assert "## Transcript" in md

    def test_contains_text(self):
        md = build_markdown(_make_result("Testing output"), "/tmp/test.wav")
        assert "Testing output" in md

    def test_contains_notes(self):
        md = build_markdown(_make_result(), "/tmp/test.wav", notes=["Note one", "Note two"])
        assert "[^1]: Note one" in md
        assert "[^2]: Note two" in md
        assert "## Notes" in md

    def test_no_notes_section_when_empty(self):
        md = build_markdown(_make_result(), "/tmp/test.wav", notes=None)
        assert "## Notes" not in md


class TestSaveTranscript:
    def test_creates_md_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "test.wav"
            wav_path.write_bytes(b"fake wav")
            md_path = save_transcript(_make_result(), wav_path)
            assert md_path.exists()
            assert md_path.suffix == ".md"
            content = md_path.read_text()
            assert "Hello world." in content


class TestCleanupAudio:
    def test_deletes_wav_when_md_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "test.wav"
            md_path = Path(tmpdir) / "test.md"
            wav_path.write_bytes(b"fake wav data")
            md_path.write_text("# Transcript\nHello.")
            assert cleanup_audio(wav_path, md_path) is True
            assert not wav_path.exists()

    def test_refuses_when_md_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "test.wav"
            md_path = Path(tmpdir) / "test.md"
            wav_path.write_bytes(b"fake wav data")
            assert cleanup_audio(wav_path, md_path) is False
            assert wav_path.exists()

    def test_refuses_when_md_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "test.wav"
            md_path = Path(tmpdir) / "test.md"
            wav_path.write_bytes(b"fake wav data")
            md_path.write_text("")
            assert cleanup_audio(wav_path, md_path) is False
            assert wav_path.exists()
