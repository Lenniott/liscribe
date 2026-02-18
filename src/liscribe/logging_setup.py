"""Logging configuration for liscribe.

Logs to both:
- ~/.config/liscribe/liscribe.log (persistent, for debugging)
- stderr (only warnings and above, to not interfere with TUI)
"""

from __future__ import annotations

import logging
from pathlib import Path

LOG_DIR = Path.home() / ".config" / "liscribe"
LOG_FILE = LOG_DIR / "liscribe.log"


def setup_logging(debug: bool = False) -> None:
    """Configure logging for the application."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("liscribe")
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # File handler — always DEBUG level for post-mortem debugging
    fh = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
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
