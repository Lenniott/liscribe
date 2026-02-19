"""Shell alias: get rc path and write alias line (shared by CLI and Preferences TUI)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Must match install.sh and cli.py
ALIAS_MARKER = "# liscribe"


def get_shell_rc_path() -> Path:
    """Path to the current shell's rc file (e.g. ~/.zshrc)."""
    shell = os.path.basename(os.environ.get("SHELL", "/bin/zsh"))
    if shell == "zsh":
        return Path.home() / ".zshrc"
    if shell == "bash":
        return Path.home() / ".bashrc"
    return Path.home() / f".{shell}rc"


def update_shell_alias(alias_name: str) -> Path | None:
    """Update shell rc so the given alias runs liscribe. Remove old liscribe alias, add new one.
    Returns the rc path if the file was updated, None otherwise.
    """
    rc = get_shell_rc_path()
    rec_path = Path(sys.executable).parent / "rec"
    if not rec_path.exists():
        rec_path = Path(sys.executable).parent / "rec.exe"
    if not rec_path.exists():
        return None
    alias_line = f"alias {alias_name}='{rec_path}'  {ALIAS_MARKER}\n"
    try:
        if rc.exists():
            lines = rc.read_text(encoding="utf-8").splitlines(keepends=True)
        else:
            lines = []
        new_lines = [line for line in lines if ALIAS_MARKER not in line]
        prefix = "\n" if new_lines else ""
        new_lines.append(prefix + alias_line)
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.write_text("".join(new_lines).rstrip() + "\n", encoding="utf-8")
        return rc
    except (OSError, IOError):
        return None
