"""Preferences — Alias: set command alias and update shell rc."""

from __future__ import annotations

from textual.containers import Vertical
from textual.widgets import Button, Input, Static

from liscribe.config import load_config, save_config
from liscribe.shell_alias import get_shell_rc_path, update_shell_alias
from liscribe.screens.base import BackScreen


class PrefsAliasScreen(BackScreen):
    """Edit command alias and write to shell rc."""

    def compose(self):
        cfg = load_config()
        alias = cfg.get("command_alias", "rec") or "rec"
        with Vertical(id="home-frame"):
            yield Static("Alias", id="home-title")
            yield Static("Command alias (used in help and shell):", id="alias-label")
            yield Input(value=alias, id="alias-input", placeholder="rec")
            yield Static(f"Updates {get_shell_rc_path()} when you save.", id="alias-hint")
            yield Button("Save and update zshrc", id="btn-save")
            yield Button("Back to Preferences", id="btn-back")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
            return
        if event.button.id == "btn-save":
            inp = self.query_one("#alias-input", Input)
            alias = inp.value.strip() or "rec"
            cfg = load_config()
            cfg["command_alias"] = alias
            save_config(cfg)
            rc = update_shell_alias(alias)
            if rc:
                self.notify(f"Updated {rc}. Run: source {rc}")
            else:
                self.notify("Config saved; could not update shell rc (rec binary not found?).")
