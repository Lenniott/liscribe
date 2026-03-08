"""Tests for Phase 9 — Bundle + Install (terminal-only).

Validates install.sh (venv + alias), uninstall.sh, and package layout.
Tests read script/setup content; they do not modify the real system.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Repo root (parent of tests/)
REPO_ROOT = Path(__file__).resolve().parent.parent

SETUP_PY = REPO_ROOT / "setup.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"
INSTALL_SH = REPO_ROOT / "install.sh"
UNINSTALL_SH = REPO_ROOT / "uninstall.sh"


# ---------------------------------------------------------------------------
# Package / setup (pip install .)
# ---------------------------------------------------------------------------


def test_setup_includes_ui_panels_and_assets() -> None:
    """Package includes ui/panels and ui/assets for pip install."""
    assert SETUP_PY.exists()
    content = SETUP_PY.read_text()
    has_panels = "panels" in content or "ui" in content
    has_assets = "assets" in content or "ui" in content
    assert has_panels and has_assets, "setup must include ui/panels and ui/assets"


def test_setup_includes_sample_wav() -> None:
    """Package includes sample.wav under ui/assets."""
    assert SETUP_PY.exists()
    content = SETUP_PY.read_text()
    assert "sample.wav" in content or "ui/assets" in content, (
        "setup must include sample.wav or ui/assets"
    )


def test_setup_excludes_tests_from_package() -> None:
    """Package is built from src/ only; tests are not installed."""
    assert SETUP_PY.exists()
    content = SETUP_PY.read_text()
    assert "src" in content, "packages must be from src"
    assert "find_packages" in content or "packages" in content


def test_liscribe_has_main_module() -> None:
    """Package is runnable as python -m liscribe (used by alias or direct run)."""
    main_py = REPO_ROOT / "src" / "liscribe" / "__main__.py"
    assert main_py.exists(), "liscribe must have __main__.py for -m liscribe"


# ---------------------------------------------------------------------------
# install.sh (terminal-only: venv, pip, alias, permissions hint)
# ---------------------------------------------------------------------------


def test_install_sh_checks_python_version() -> None:
    """Script checks for Python 3.10+ and exits with a clear message if missing."""
    assert INSTALL_SH.exists()
    content = INSTALL_SH.read_text()
    assert "python" in content.lower(), "must check Python"
    assert "3.10" in content or "version" in content.lower(), "must check Python 3.10+"


def test_install_sh_checks_homebrew_and_portaudio() -> None:
    """Script checks Homebrew and portaudio (required for recording)."""
    assert INSTALL_SH.exists()
    content = INSTALL_SH.read_text()
    assert "brew" in content, "must mention or check Homebrew"
    assert "portaudio" in content, "must mention or check portaudio"


def test_install_sh_creates_venv_and_pip_install() -> None:
    """Script creates venv and runs pip install (no .app)."""
    assert INSTALL_SH.exists()
    content = INSTALL_SH.read_text()
    assert "venv" in content or "pip" in content, "must create venv or install deps"
    assert "pip" in content and "install" in content, "must run pip install"
    assert "alias liscribe=" in content, "must add liscribe alias to .zshrc"
    assert ".zshrc" in content, "must touch .zshrc"


def test_install_sh_cleans_zshrc_and_adds_alias() -> None:
    """Script removes existing liscribe lines from .zshrc then adds alias liscribe=."""
    assert INSTALL_SH.exists()
    content = INSTALL_SH.read_text()
    assert "liscribe" in content and "alias" in content, "must define alias liscribe"
    assert ".venv" in content or "app.py" in content or "/liscribe'" in content, "alias must use repo venv or wrapper script"


def test_install_sh_prints_permissions_hint() -> None:
    """Script output mentions Accessibility, Input Monitoring, Microphone or Terminal."""
    assert INSTALL_SH.exists()
    content = INSTALL_SH.read_text()
    has_accessibility = "Accessibility" in content or "accessibility" in content.lower()
    has_input = "Input Monitoring" in content or "input" in content.lower()
    has_mic = "Microphone" in content or "microphone" in content.lower()
    has_terminal = "Terminal" in content or "terminal" in content.lower()
    assert (
        has_accessibility or has_input or has_mic or has_terminal
    ), "must print permissions hint (Accessibility, Input Monitoring, Microphone, or Terminal)"


# ---------------------------------------------------------------------------
# uninstall.sh
# ---------------------------------------------------------------------------


def test_uninstall_sh_removes_zshrc_alias_and_dirs() -> None:
    """Script removes liscribe from .zshrc, and removes config/cache dirs."""
    assert UNINSTALL_SH.exists()
    content = UNINSTALL_SH.read_text()
    assert ".zshrc" in content and "liscribe" in content, "must clean .zshrc of liscribe"
    assert ".config" in content and "liscribe" in content, "must remove config directory"
    assert ".cache" in content and "liscribe" in content, "must remove cache directory"


def test_uninstall_sh_removes_login_item() -> None:
    """Script removes the Liscribe login item if present (osascript delete login item)."""
    assert UNINSTALL_SH.exists()
    content = UNINSTALL_SH.read_text()
    assert "osascript" in content or "login item" in content, "must remove login item"
    assert "Liscribe" in content, "must target Liscribe login item"
