"""Preferences — Save location: default folder for recordings and transcripts."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from liscribe.config import load_config, save_config
from liscribe.screens.base import BackScreen


class PrefsSaveLocationScreen(BackScreen):
    """Set default save folder."""

    def compose(self):
        cfg = load_config()
        folder = cfg.get("save_folder", "~/transcripts") or "~/transcripts"
        with Vertical(classes="screen-frame"):
            with Horizontal(classes="top-bar compact"):
                yield Static("liscribe", classes="brand")
                yield Static("Save location", classes="top-bar-section")
            with Vertical(classes="screen-body"):
                yield Static("Default save folder (recordings and transcripts):")
                yield Input(value=folder, id="save-input", placeholder="~/transcripts")
                yield Static(
                    "Use --here when starting a recording to save to ./docs/transcripts in the current directory.",
                    classes="screen-body-subtitle",
                )
                yield Button("Save", id="btn-save", classes="btn primary")
                yield Static("", classes="spacer")
                yield Button("Back to Preferences", id="btn-back", classes="btn secondary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
            return
        if event.button.id == "btn-save":
            inp = self.query_one("#save-input", Input)
            folder = inp.value.strip() or "~/transcripts"
            cfg = load_config()
            cfg["save_folder"] = folder
            save_config(cfg)
            self.notify(f"Save folder set to {folder}")
