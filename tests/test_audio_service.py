"""Tests for AudioService — recording lifecycle and cancel behaviour."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from liscribe.services.audio_service import AudioService
from liscribe.services.config_service import ConfigService


@pytest.fixture()
def mock_config():
    cfg = MagicMock(spec=ConfigService)
    cfg.save_folder = "~/transcripts"
    cfg.default_mic = None
    return cfg


@pytest.fixture()
def svc(mock_config):
    return AudioService(mock_config)


def _mock_active_session(svc, wav_path: str) -> None:
    """Set up svc as if a recording is in progress."""
    session = MagicMock()
    session._stop_requested = threading.Event()
    thread = MagicMock()
    thread.is_alive.return_value = True
    svc._session = session
    svc._thread = thread
    svc._wav_path = wav_path


# ---------------------------------------------------------------------------
# list_mics
# ---------------------------------------------------------------------------

class TestListMics:
    def test_returns_a_list(self, svc):
        with patch("liscribe.services.audio_service.list_input_devices", return_value=[]):
            assert isinstance(svc.list_mics(), list)

    def test_delegates_to_list_input_devices(self, svc):
        expected = [{"index": 0, "name": "Built-in Mic"}]
        with patch("liscribe.services.audio_service.list_input_devices", return_value=expected) as m:
            result = svc.list_mics()
        m.assert_called_once()
        assert result == expected


# ---------------------------------------------------------------------------
# is_recording
# ---------------------------------------------------------------------------

class TestIsRecording:
    def test_false_initially(self, svc):
        assert svc.is_recording is False

    def test_true_when_thread_alive(self, svc):
        _mock_active_session(svc, "/tmp/test.wav")
        assert svc.is_recording is True

    def test_false_when_thread_dead(self, svc):
        _mock_active_session(svc, "/tmp/test.wav")
        svc._thread.is_alive.return_value = False
        assert svc.is_recording is False


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

class TestStart:
    def test_raises_if_already_recording(self, svc):
        _mock_active_session(svc, "/tmp/test.wav")
        with pytest.raises(RuntimeError, match="already active"):
            svc.start()

    def test_start_when_idle_does_not_raise(self, svc):
        with patch("liscribe.services.audio_service.RecordingSession") as MockSession:
            MockSession.return_value._stop_requested = threading.Event()
            MockSession.return_value.start.return_value = None
            svc.start()
            svc.stop()


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

class TestStop:
    def test_stop_on_idle_returns_none(self, svc):
        assert svc.stop() is None

    def test_stop_returns_wav_path(self, svc):
        _mock_active_session(svc, "/tmp/rec.wav")
        result = svc.stop()
        assert result == "/tmp/rec.wav"

    def test_stop_clears_session_state(self, svc):
        _mock_active_session(svc, "/tmp/rec.wav")
        svc.stop()
        assert svc._session is None
        assert svc._thread is None
        assert svc._wav_path is None

    def test_stop_signals_stop_event(self, svc):
        _mock_active_session(svc, "/tmp/rec.wav")
        stop_event = svc._session._stop_requested
        svc.stop()
        assert stop_event.is_set()


# ---------------------------------------------------------------------------
# get_levels
# ---------------------------------------------------------------------------

class TestGetLevels:
    def test_returns_empty_when_not_recording(self, svc):
        assert svc.get_levels() == []

    def test_returns_empty_when_no_chunks_yet(self, svc):
        _mock_active_session(svc, "/tmp/rec.wav")
        svc._session._lock = threading.Lock()
        svc._session._mic_chunks = []
        assert svc.get_levels() == []


# ---------------------------------------------------------------------------
# cancel — must delete files, not just stop
# ---------------------------------------------------------------------------

class TestCancel:
    def test_cancel_on_idle_is_safe(self, svc):
        svc.cancel()  # must not raise

    def test_cancel_deletes_single_wav_file(self, svc, tmp_path):
        wav = tmp_path / "2024-01-01_12-00-00.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 36)
        _mock_active_session(svc, str(wav))
        svc.cancel()
        assert not wav.exists()

    def test_cancel_deletes_dual_source_session_directory(self, svc, tmp_path):
        session_dir = tmp_path / "2024-01-01_12-00-00"
        session_dir.mkdir()
        (session_dir / "session.json").write_text("{}")
        mic_wav = session_dir / "mic.wav"
        mic_wav.write_bytes(b"RIFF" + b"\x00" * 36)
        (session_dir / "speaker.wav").write_bytes(b"RIFF" + b"\x00" * 36)
        _mock_active_session(svc, str(mic_wav))
        svc.cancel()
        assert not session_dir.exists()

    def test_cancel_leaves_no_wav_path_after(self, svc, tmp_path):
        wav = tmp_path / "rec.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 36)
        _mock_active_session(svc, str(wav))
        svc.cancel()
        assert svc._wav_path is None

    def test_stop_does_not_delete_file(self, svc, tmp_path):
        """stop() preserves the file; cancel() deletes it."""
        wav = tmp_path / "rec.wav"
        wav.write_bytes(b"RIFF" + b"\x00" * 36)
        _mock_active_session(svc, str(wav))
        svc.stop()
        assert wav.exists()
