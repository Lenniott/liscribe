"""Tests for output module."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from liscribe.notes import Note
from liscribe.transcriber import TranscriptionResult
from liscribe.output import (
    build_markdown,
    save_transcript,
    cleanup_audio,
    _find_segment_for_note,
    _build_annotated_transcript,
)


def _make_result(text: str = "Hello world.") -> TranscriptionResult:
    return TranscriptionResult(
        text=text,
        segments=[{"start": 0.0, "end": 1.0, "text": text}],
        language="en",
        duration=2.0,
    )


def _make_multi_segment_result() -> TranscriptionResult:
    segments = [
        {"start": 0.0, "end": 2.5, "text": "That's quite nice"},
        {"start": 2.5, "end": 4.0, "text": "um, here it is"},
    ]
    text = " ".join(s["text"] for s in segments)
    return TranscriptionResult(text=text, segments=segments, language="en", duration=4.0)


def _make_source_segment_result() -> TranscriptionResult:
    segments = [
        {"start": 1.2, "end": 2.0, "text": "Okay let's start.", "source": "mic", "speaker": "YOU"},
        {"start": 2.9, "end": 3.5, "text": "Sure, I can see your screen now.", "source": "speaker", "speaker": "THEM"},
    ]
    return TranscriptionResult(
        text="YOU: Okay let's start. THEM: Sure, I can see your screen now.",
        segments=segments,
        language="en",
        duration=5.0,
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
        notes = [
            Note(index=1, text="Note one", timestamp=0.5),
            Note(index=2, text="Note two", timestamp=0.8),
        ]
        md = build_markdown(_make_result(), "/tmp/test.wav", notes=notes)
        assert "[^1]: Note one" in md
        assert "[^2]: Note two" in md
        assert "## Notes" in md

    def test_no_notes_section_when_empty(self):
        md = build_markdown(_make_result(), "/tmp/test.wav", notes=None)
        assert "## Notes" not in md

    def test_annotated_transcript_in_markdown(self):
        result = _make_multi_segment_result()
        notes = [Note(index=1, text="nice one", timestamp=1.0)]
        md = build_markdown(result, "/tmp/test.wav", notes=notes)
        assert "[That's quite nice][1]" in md
        assert "um, here it is" in md
        assert "[^1]: nice one" in md

    def test_no_annotation_without_segments(self):
        result = TranscriptionResult(
            text="Plain text", segments=[], language="en", duration=1.0,
        )
        notes = [Note(index=1, text="a note", timestamp=0.5)]
        md = build_markdown(result, "/tmp/test.wav", notes=notes)
        assert "Plain text" in md
        assert "[^1]: a note" in md

    def test_source_based_chronological_transcript(self):
        with patch(
            "liscribe.config.load_config",
            return_value={"whisper_model": "base", "source_include_timestamps": False},
        ):
            md = build_markdown(_make_source_segment_result(), "/tmp/mic.wav")
        assert "diarization: source-based" in md
        assert "In (mic): Okay let's start." in md
        assert "Out (speaker): Sure, I can see your screen now." in md


class TestSegmentNoteMapping:
    def test_note_inside_segment(self):
        segments = [{"start": 0.0, "end": 2.0, "text": "first"}, {"start": 2.0, "end": 4.0, "text": "second"}]
        assert _find_segment_for_note(segments, 1.0) == 0
        assert _find_segment_for_note(segments, 3.0) == 1

    def test_note_at_segment_boundary(self):
        segments = [{"start": 0.0, "end": 2.0, "text": "first"}, {"start": 2.0, "end": 4.0, "text": "second"}]
        assert _find_segment_for_note(segments, 2.0) in (0, 1)

    def test_note_before_all_segments(self):
        segments = [{"start": 1.0, "end": 3.0, "text": "only"}]
        assert _find_segment_for_note(segments, 0.0) == 0

    def test_note_after_all_segments(self):
        segments = [{"start": 0.0, "end": 2.0, "text": "only"}]
        assert _find_segment_for_note(segments, 5.0) == 0

    def test_note_in_gap_between_segments(self):
        segments = [{"start": 0.0, "end": 1.0, "text": "a"}, {"start": 3.0, "end": 4.0, "text": "b"}]
        assert _find_segment_for_note(segments, 1.5) == 0
        assert _find_segment_for_note(segments, 2.5) == 1


class TestAnnotatedTranscript:
    def test_single_note_on_segment(self):
        segments = [
            {"start": 0.0, "end": 2.0, "text": "hello world"},
            {"start": 2.0, "end": 4.0, "text": "goodbye"},
        ]
        notes = [Note(index=1, text="greeting", timestamp=1.0)]
        text = _build_annotated_transcript(segments, notes)
        assert "[hello world][1]" in text
        assert "goodbye" in text
        assert "[goodbye]" not in text

    def test_multiple_notes_on_same_segment(self):
        segments = [{"start": 0.0, "end": 3.0, "text": "long segment"}]
        notes = [
            Note(index=1, text="first", timestamp=0.5),
            Note(index=2, text="second", timestamp=1.5),
        ]
        text = _build_annotated_transcript(segments, notes)
        assert "[long segment][1][2]" in text

    def test_no_notes_plain_text(self):
        segments = [{"start": 0.0, "end": 2.0, "text": "just text"}]
        text = _build_annotated_transcript(segments, [])
        assert text == "just text"

    def test_notes_on_different_segments(self):
        segments = [
            {"start": 0.0, "end": 2.5, "text": "That's quite nice"},
            {"start": 2.5, "end": 4.0, "text": "um, here it is"},
        ]
        notes = [
            Note(index=1, text="here is anote", timestamp=1.0),
            Note(index=2, text="nisrc", timestamp=3.0),
        ]
        text = _build_annotated_transcript(segments, notes)
        assert "[That's quite nice][1]" in text
        assert "[um, here it is][2]" in text


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

    def test_respects_filename_stem_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_path = Path(tmpdir) / "mic.wav"
            wav_path.write_bytes(b"fake wav")
            md_path = save_transcript(_make_result(), wav_path, filename_stem="session_123")
            assert md_path.name == "session_123.md"


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
