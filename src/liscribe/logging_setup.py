"""Logging configuration for liscribe.

Logs to both:
- ~/.config/liscribe/liscribe.log (persistent, for debugging — 5 MB cap, 2 backups)
- stderr (only warnings and above, to not interfere with TUI)
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path.home() / ".config" / "liscribe"
LOG_FILE = LOG_DIR / "liscribe.log"

_LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_LOG_BACKUP_COUNT = 2


def setup_logging(debug: bool = False) -> None:
    """Configure logging for the application."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("liscribe")
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # File handler — always DEBUG level for post-mortem debugging.
    # Rotates at 5 MB, keeps 2 backups (liscribe.log.1, liscribe.log.2).
    fh = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=_LOG_MAX_BYTES,
        backupCount=_LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(fh)

    # Stderr handler — only warnings unless debug mode
    sh = logging.StreamHandler()
    sh.setLevel(logging.DEBUG if debug else logging.WARNING)
    sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    root.addHandler(sh)
