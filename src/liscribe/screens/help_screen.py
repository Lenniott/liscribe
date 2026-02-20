"""Help screen — same content as rec --help."""

from __future__ import annotations

from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Static

from liscribe.config import load_config
from liscribe.screens.base import BackScreen


class HelpScreen(BackScreen):
    """Show rec --help content; Back to Home."""

    def compose(self):
        with Vertical(classes="screen-frame"):
            with Horizontal(classes="top-bar compact"):
                yield Static("liscribe", classes="brand")
                yield Static("Help", classes="top-bar-section")
            with Vertical(classes="screen-body"):
                with ScrollableContainer(id="help-scroll", classes="scroll-fill"):
                    yield Static("", id="help-text")
                yield Button("Back to Home", id="btn-back", classes="btn secondary")

    def on_mount(self) -> None:
        from liscribe.cli import get_help_text
        cfg = load_config()
        prog = cfg.get("command_alias", "rec") or "rec"
        text = get_help_text(prog_name=prog)
        self.query_one("#help-text", Static).update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
