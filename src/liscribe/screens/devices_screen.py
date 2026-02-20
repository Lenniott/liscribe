"""Devices screen — list input devices."""

from __future__ import annotations

from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Static

from liscribe.recorder import list_input_devices
from liscribe.screens.base import BackScreen


class DevicesScreen(BackScreen):
    """List audio input devices; Back to Home."""

    def compose(self):
        with Vertical(classes="screen-frame"):
            with Horizontal(classes="top-bar compact"):
                yield Static("liscribe", classes="brand")
                yield Static("Input devices", classes="top-bar-section")
            with Vertical(classes="screen-body"):
                with ScrollableContainer(id="devices-list", classes="scroll-fill"):
                    yield Static("", id="devices-text")
                yield Button("Back to Home", id="btn-back", classes="btn secondary")

    def on_mount(self) -> None:
        try:
            devices = list_input_devices()
            lines = []
            for dev in devices:
                default = " (default)" if dev.get("is_default") else ""
                lines.append(
                    f"[{dev['index']}] {dev['name']} "
                    f"({dev['channels']}ch, {dev['sample_rate']}Hz){default}"
                )
            self.query_one("#devices-text", Static).update("\n".join(lines) or "No input devices found.")
        except Exception as e:
            self.query_one("#devices-text", Static).update(f"Error: {e}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
