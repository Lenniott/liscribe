"""Tests for CLI folder resolution helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("rich")

from liscribe import cli


def test_resolve_folder_prefers_explicit_folder(tmp_path: Path) -> None:
    explicit = str(tmp_path / "custom")
    assert cli._resolve_folder(explicit, here=False) == explicit


def test_resolve_folder_uses_here_flag(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "load_config", lambda: {"save_folder": "~/transcripts"})
    assert cli._resolve_folder(None, here=True) == str(tmp_path / "docs" / "transcripts")


def test_resolve_folder_uses_here_default_from_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: {
            "record_here_by_default": True,
            "save_folder": "/tmp/ignored",
        },
    )
    assert cli._resolve_folder(None, here=False) == str(tmp_path / "docs" / "transcripts")


def test_resolve_folder_uses_config_save_folder_when_here_default_off(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "load_config",
        lambda: {
            "record_here_by_default": False,
            "save_folder": "~/transcripts-2",
        },
    )
    assert cli._resolve_folder(None, here=False) == "~/transcripts-2"
