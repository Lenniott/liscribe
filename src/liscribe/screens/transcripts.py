"""Transcripts screen — list .md files from save_folder, copy to clipboard."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from textual.containers import Vertical, ScrollableContainer
from textual.widgets import Button, Static

from liscribe.config import load_config
from liscribe.output import copy_to_clipboard
from liscribe.screens.base import BackScreen


class TranscriptsScreen(BackScreen):
    """List transcripts; each row has copy to clipboard."""

    def compose(self):
        with Vertical(id="home-frame"):
            yield Static("liscribe", id="home-title")
            yield Static("Transcripts", id="home-subtitle")
            with ScrollableContainer(id="transcripts-list"):
                pass  # filled in on_mount
            yield Button("Back to Home", id="btn-back")

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        cfg = load_config()
        folder = Path(cfg.get("save_folder", "~/transcripts")).expanduser().resolve()
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
        md_files = sorted(folder.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

        container = self.query_one("#transcripts-list", ScrollableContainer)
        container.remove_children()

        if not md_files:
            container.mount(Static("No transcripts yet. Record and save to see them here."))
            return

        for path in md_files:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            date_str = mtime.strftime("%d-%m-%Y")
            row = TranscriptRow(path=path, date_str=date_str)
            container.mount(row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
            return
        if event.button.id and event.button.id.startswith("copy-"):
            stem = event.button.id.replace("copy-", "")
            folder = Path(load_config().get("save_folder", "~/transcripts")).expanduser().resolve()
            path = folder / f"{stem}.md"
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
                if copy_to_clipboard(text):
                    self.notify("Copied to clipboard")
                else:
                    self.notify("Could not copy to clipboard", severity="error")
            else:
                self.notify("File not found", severity="error")


class TranscriptRow(Vertical):
    """One transcript row: date, filename, copy button."""

    def __init__(self, path: Path, date_str: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.path = path
        self.date_str = date_str

    def compose(self):
        # Use a stable id for the row so we can find it for copy
        row_id = self.path.stem
        self.id = f"row-{row_id}"
        yield Static(f"{self.date_str}   {self.path.name}", id=f"label-{row_id}")
        yield Button("Copy to clipboard", id=f"copy-{row_id}")
