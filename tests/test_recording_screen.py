"""Tests for recording screen speaker toggle behavior."""

from unittest.mock import Mock

import pytest

pytest.importorskip("textual")

from liscribe.screens.recording import RecordingScreen


def test_remove_speaker_capture_uses_session_disable() -> None:
    screen = RecordingScreen(folder=".", speaker=True)
    session = Mock()

    screen.session = session
    screen.speaker = True
    screen.notify = Mock()

    screen.action_remove_speaker_capture()

    session.disable_speaker_capture.assert_called_once_with()
    assert screen.speaker is False


def test_remove_speaker_capture_noop_when_already_off() -> None:
    screen = RecordingScreen(folder=".", speaker=False)
    session = Mock()

    screen.session = session
    screen.speaker = False
    screen.notify = Mock()

    screen.action_remove_speaker_capture()

    session.disable_speaker_capture.assert_not_called()
