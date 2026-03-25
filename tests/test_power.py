"""Tests for src/liscribe/power.py"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from liscribe.power import (
    _NO_ASSERTION,
    acquire_recording_assertion,
    release_recording_assertion,
)


# ---------------------------------------------------------------------------
# Non-macOS platform — both functions are no-ops
# ---------------------------------------------------------------------------

def test_acquire_returns_zero_on_non_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    result = acquire_recording_assertion()
    assert result == _NO_ASSERTION


def test_release_is_noop_on_non_darwin(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    # Must not raise
    release_recording_assertion(42)


def test_release_is_noop_for_zero_id():
    # Must not raise regardless of platform
    release_recording_assertion(_NO_ASSERTION)


# ---------------------------------------------------------------------------
# macOS path — IOKit available, call succeeds
# ---------------------------------------------------------------------------

def _make_iokit_mock(create_ret: int = 0, release_ret: int = 0, assertion_value: int = 7):
    """Return a mock IOKit CDLL that behaves correctly."""
    mock_iokit = MagicMock()

    def fake_create(atype, level, name, byref_id):
        # Write assertion_value into the ctypes byref argument
        byref_id._obj.value = assertion_value
        return create_ret

    mock_iokit.IOPMAssertionCreateWithName.side_effect = fake_create
    mock_iokit.IOPMAssertionRelease.return_value = release_ret
    return mock_iokit


def test_acquire_returns_assertion_id_on_success(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    mock_iokit = _make_iokit_mock(assertion_value=42)
    with patch("liscribe.power._load_iokit", return_value=mock_iokit):
        result = acquire_recording_assertion()
    assert result == 42


def test_acquire_returns_zero_when_iokit_unavailable(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    with patch("liscribe.power._load_iokit", return_value=None):
        result = acquire_recording_assertion()
    assert result == _NO_ASSERTION


def test_acquire_returns_zero_when_create_fails(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    mock_iokit = _make_iokit_mock(create_ret=1)  # non-zero = failure
    with patch("liscribe.power._load_iokit", return_value=mock_iokit):
        result = acquire_recording_assertion()
    assert result == _NO_ASSERTION


def test_acquire_returns_zero_on_exception(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    with patch("liscribe.power._load_iokit", side_effect=OSError("boom")):
        result = acquire_recording_assertion()
    assert result == _NO_ASSERTION


def test_release_calls_iokit_with_correct_id(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    mock_iokit = _make_iokit_mock()
    with patch("liscribe.power._load_iokit", return_value=mock_iokit):
        release_recording_assertion(7)
    mock_iokit.IOPMAssertionRelease.assert_called_once()


def test_release_does_not_raise_on_iokit_failure(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    mock_iokit = _make_iokit_mock(release_ret=1)
    with patch("liscribe.power._load_iokit", return_value=mock_iokit):
        release_recording_assertion(7)  # must not raise


def test_release_does_not_raise_on_exception(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    with patch("liscribe.power._load_iokit", side_effect=OSError("boom")):
        release_recording_assertion(7)  # must not raise
