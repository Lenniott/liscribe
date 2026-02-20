"""Preferences — General: clipboard, alias, update/uninstall commands."""

from __future__ import annotations

from pathlib import Path

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static, Switch

from liscribe.config import load_config, save_config
from liscribe.screens.base import BackScreen
from liscribe.shell_alias import get_shell_rc_path, update_shell_alias


class PrefsGeneralScreen(BackScreen):
    """General settings and maintenance commands."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._repo_root = Path(__file__).resolve().parents[3]

    def compose(self):
        cfg = load_config()
        alias = cfg.get("command_alias", "rec") or "rec"
        auto_clipboard = bool(cfg.get("auto_clipboard", True))

        with Vertical(classes="screen-frame"):
            with Horizontal(classes="top-bar compact"):
                yield Static("liscribe", classes="brand")
                yield Static("General", classes="top-bar-section")
            with Vertical(classes="screen-body"):
                yield Static("Copy transcript to clipboard after transcription:")
                yield Switch(value=auto_clipboard, id="clipboard-switch")
                yield Static("Command alias word (used in help and shell):")
                yield Input(value=alias, id="alias-input", placeholder="rec")
                yield Static(f"Updates {get_shell_rc_path()} when you save.", classes="screen-body-subtitle")
                yield Button("Save general settings", id="btn-save", classes="btn primary")
                yield Static("", classes="screen-body-subtitle")
                yield Static("Update command:", classes="screen-body-subtitle")
                yield Static(
                    f"cd {self._repo_root} && git pull --ff-only && ./install.sh",
                    classes="screen-body-subtitle",
                )
                yield Static("Uninstall command:", classes="screen-body-subtitle")
                yield Static(f"cd {self._repo_root} && ./uninstall.sh", classes="screen-body-subtitle")
                yield Static("", classes="spacer")
                yield Button("Back to Preferences", id="btn-back", classes="btn secondary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
            return
        if event.button.id != "btn-save":
            return

        alias = self.query_one("#alias-input", Input).value.strip() or "rec"
        auto_clipboard = self.query_one("#clipboard-switch", Switch).value

        cfg = load_config()
        cfg["command_alias"] = alias
        cfg["auto_clipboard"] = bool(auto_clipboard)
        save_config(cfg)

        rc = update_shell_alias(alias)
        if rc:
            self.notify(f"Saved. Alias updated in {rc}")
        else:
            self.notify("Saved. Could not update shell rc (rec binary not found?).")
