"""Tests for global/back key binding coverage."""

from __future__ import annotations

import pytest

pytest.importorskip("textual")

from liscribe.screens.base import BACK_BINDINGS, RECORDING_BINDINGS
from liscribe.screens.modals import ConfirmCancelScreen, MicSelectScreen
from liscribe.screens.transcribing import TranscribingScreen


def _binding_exists(bindings, key: str, action: str, *, priority: bool | None = None) -> bool:
    for binding in bindings:
        if binding.key == key and binding.action == action:
            if priority is None or bool(binding.priority) == priority:
                return True
    return False


def test_back_screens_support_ctrl_c_back() -> None:
    assert _binding_exists(BACK_BINDINGS, "ctrl+c", "back", priority=True)


def test_recording_ctrl_c_prioritizes_cancel() -> None:
    assert _binding_exists(RECORDING_BINDINGS, "ctrl+c", "cancel", priority=True)


def test_modal_ctrl_c_bindings() -> None:
    assert _binding_exists(MicSelectScreen.BINDINGS, "ctrl+c", "cancel", priority=True)
    assert _binding_exists(ConfirmCancelScreen.BINDINGS, "ctrl+c", "yes", priority=True)


def test_transcribing_supports_ctrl_c_back() -> None:
    assert _binding_exists(TranscribingScreen.BINDINGS, "ctrl+c", "back", priority=True)
