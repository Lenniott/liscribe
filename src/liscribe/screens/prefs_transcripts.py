"""Preferences — Transcripts: save path, --here default, open app."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from liscribe.config import load_config, save_config
from liscribe.screens.base import BackScreen


class PrefsTranscriptsScreen(BackScreen):
    """Transcript/output-related settings."""

    def compose(self):
        cfg = load_config()
        folder = cfg.get("save_folder", "~/transcripts") or "~/transcripts"
        self._use_here_default = bool(cfg.get("record_here_by_default", False))
        open_app = str(cfg.get("open_transcript_app", "cursor") or "cursor")

        with Vertical(classes="screen-frame"):
            with Horizontal(classes="top-bar compact"):
                yield Static("liscribe", classes="brand")
                yield Static("Transcripts", classes="top-bar-section")
            with Vertical(classes="screen-body"):
                yield Static("", classes="spacer")
                yield Static("Default save path (recordings and transcripts):")
                yield Input(value=folder, id="save-input", placeholder="~/transcripts")
                yield Static("", classes="margin-small")
                with Horizontal(classes="row row-height-1"):
                    yield Static("Use --here path by default when pressing Record:")
                    yield Button(
                        "Deactivate" if self._use_here_default else "Activate",
                        id="here-default-btn",
                        classes="btn secondary inline" if not self._use_here_default else "btn danger inline",
                    )
                yield Static("", classes="margin-small")
                yield Static("When enabled, Record saves to ./docs/transcripts from the current directory.", classes="screen-body-subtitle")
                yield Static("", classes="margin-small")
                yield Static("Default app for 'Open transcript' (e.g. cursor, code, code -r, default):")
                yield Input(value=open_app, id="open-app-input", placeholder="cursor")
                yield Static("", classes="margin-small")
            with Horizontal(classes="screen-body-footer"):
                    yield Button("^c Back to preferences", id="btn-back", classes="btn secondary inline hug-row")
                    yield Static("", classes="spacer-row")
                    yield Button("Save", id="btn-save", classes="btn primary inline hug-row")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
            return
        if event.button.id == "here-default-btn":
            self._use_here_default = not self._use_here_default
            btn = event.button
            btn.label = "Deactivate" if self._use_here_default else "Activate"
            btn.classes = "btn danger inline" if self._use_here_default else "btn secondary inline"
            return
        if event.button.id != "btn-save":
            return

        folder = self.query_one("#save-input", Input).value.strip() or "~/transcripts"
        use_here_default = self._use_here_default
        open_app = self.query_one("#open-app-input", Input).value.strip() or "cursor"

        cfg = load_config()
        cfg["save_folder"] = folder
        cfg["record_here_by_default"] = bool(use_here_default)
        cfg["open_transcript_app"] = open_app
        save_config(cfg)
        self.notify("Transcript settings saved")
