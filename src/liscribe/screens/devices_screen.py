"""Devices screen — list input devices."""

from __future__ import annotations

from textual.containers import Vertical, ScrollableContainer
from textual.widgets import Button, Static

from liscribe.recorder import list_input_devices
from liscribe.screens.base import BackScreen


class DevicesScreen(BackScreen):
    """List audio input devices; Back to Home."""

    def compose(self):
        with Vertical(id="home-frame"):
            yield Static("Input devices", id="home-title")
            with ScrollableContainer(id="devices-list"):
                yield Static("", id="devices-text")
            yield Button("Back to Home", id="btn-back")

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
