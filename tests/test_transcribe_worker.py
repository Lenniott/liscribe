"""Tests for transcribe_worker helper behavior."""

from pathlib import Path

from liscribe.transcribe_worker import _load_dual_source_session


class TestLoadDualSourceSession:
    def test_returns_none_for_non_mic_filename(self, tmp_path: Path):
        audio_path = tmp_path / "recording.wav"
        audio_path.write_bytes(b"x")
        assert _load_dual_source_session(audio_path) is None

    def test_returns_none_when_session_files_missing(self, tmp_path: Path):
        session_dir = tmp_path / "2026-01-01_00-00-00"
        session_dir.mkdir()
        mic = session_dir / "mic.wav"
        mic.write_bytes(b"x")
        assert _load_dual_source_session(mic) is None

    def test_loads_session_metadata(self, tmp_path: Path):
        session_dir = tmp_path / "2026-01-01_00-00-00"
        session_dir.mkdir()
        mic = session_dir / "mic.wav"
        speaker = session_dir / "speaker.wav"
        meta = session_dir / "session.json"
        mic.write_bytes(b"x")
        speaker.write_bytes(b"y")
        meta.write_text('{"offset_correction_seconds": 0.25}', encoding="utf-8")

        result = _load_dual_source_session(mic)
        assert result is not None
        assert result["mic_audio_path"] == mic
        assert result["speaker_audio_path"] == speaker
        assert result["session_json_path"] == meta
        assert result["speaker_offset_seconds"] == 0.25
