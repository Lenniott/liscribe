"""Preferences — Microphone: view and set the default input device."""

from __future__ import annotations

import sounddevice as sd
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Static

from liscribe.config import load_config, save_config
from liscribe.recorder import list_input_devices
from liscribe.screens.base import BackScreen
from liscribe.screens.top_bar import TopBar


class PrefsMicrophoneScreen(BackScreen):
    """Set or clear the preferred default input device."""

    def compose(self):
        cfg = load_config()
        current_mic = cfg.get("default_mic")
        current_label = current_mic if current_mic else "System default"

        with Vertical(classes="screen-frame"):
            yield TopBar(variant="compact", section="Microphone")
            with ScrollableContainer(classes="scroll-fill"):
                yield Static("")

                status = Static(
                    f"  Current default: {current_label}",
                    id="mic-current-label",
                )
                status.border_title = "Default microphone"
                status.border_subtitle = (
                    "Used when recording starts · overridden by --mic flag"
                )
                with Horizontal(classes="top-container"):
                    yield status

                yield Static("")

                with Vertical(id="mic-device-list", classes="hug-container"):
                    pass  # populated in on_mount

                yield Static("")

                with Horizontal(classes="hug-container"):
                    yield Button(
                        "Clear (use system default)",
                        id="btn-clear-mic",
                        classes="btn btn-secondary btn-inline",
                    )

                yield Static("")

            with Horizontal(classes="footer-container"):
                yield Static("", classes="spacer-x")
                yield Button(
                    "Back",
                    id="btn-back",
                    classes="btn btn-secondary btn-inline fixed-width",
                )

    def on_mount(self) -> None:
        self._refresh_device_list()

    def _refresh_device_list(self) -> None:
        cfg = load_config()
        current_mic = cfg.get("default_mic")
        container = self.query_one("#mic-device-list", Vertical)
        container.remove_children()
        devices = list_input_devices()
        for dev in devices:
            is_current = bool(
                current_mic
                and current_mic.lower().strip() == dev["name"].lower().strip()
            )
            variant = "btn-primary" if is_current else "btn-secondary"
            label = f"[{dev['index']}] {dev['name']} ({dev['channels']}ch, {dev['sample_rate']}Hz)"
            btn = Button(
                label,
                id=f"mic-dev-{dev['index']}",
                classes=f"btn {variant} btn-inline",
            )
            container.mount(btn)

    def _update_status_label(self, name: str | None) -> None:
        label = name if name else "System default"
        try:
            self.query_one("#mic-current-label", Static).update(
                f"  Current default: {label}"
            )
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-back":
            self.action_back()
            return
        if bid == "btn-clear-mic":
            cfg = load_config()
            cfg["default_mic"] = None
            save_config(cfg)
            self._update_status_label(None)
            self._refresh_device_list()
            self.notify("Default mic cleared — will use system default.")
            return
        if bid and bid.startswith("mic-dev-"):
            idx = int(bid.replace("mic-dev-", ""))
            dev_info = sd.query_devices(idx)
            name = dev_info["name"]
            cfg = load_config()
            cfg["default_mic"] = name
            save_config(cfg)
            self._update_status_label(name)
            self._refresh_device_list()
            self.notify(f"Default mic set to: {name}")
