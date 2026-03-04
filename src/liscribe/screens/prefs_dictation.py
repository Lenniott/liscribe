"""Preferences — Dictation: model, hotkey, system sounds.

All settings save immediately on interaction and confirm with a notify() toast.
There is no separate Save button — this matches the prefs_whisper.py pattern
where button-style selections take effect instantly.
"""

from __future__ import annotations

import logging

from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Button, Static, Switch

from liscribe.config import load_config, save_config
from liscribe.dictation import VALID_HOTKEYS
from liscribe.screens.base import BackScreen
from liscribe.screens.top_bar import TopBar
from liscribe.transcriber import WHISPER_MODEL_ORDER, is_model_available

logger = logging.getLogger(__name__)

# Ordered tuple of (config-id, display-label) derived from the single source of truth
_HOTKEY_ITEMS: tuple[tuple[str, str], ...] = tuple(VALID_HOTKEYS.items())


class PrefsDictationScreen(BackScreen):
    """Dictation settings: model, hotkey, sounds.

    All changes take effect immediately (no Save step).
    """

    def compose(self):
        cfg = load_config()
        current_model = cfg.get("dictation_model", "base")
        current_hotkey = cfg.get("dictation_hotkey", "right_option")
        sounds_on = bool(cfg.get("dictation_sounds", True))
        auto_enter_on = bool(cfg.get("dictation_auto_enter", True))
        alias = cfg.get("command_alias", "rec") or "rec"

        with Vertical(classes="screen-frame"):
            yield TopBar(variant="compact", section="Dictation")
            with ScrollableContainer(classes="scroll-fill"):
                yield Static("")

                # ── Model ──────────────────────────────────────────────
                with Horizontal(classes="strip"):
                    yield Static("", classes="model-col-mark")
                    yield Static("Model", classes="model-col-model")
                    yield Static("Status", classes="model-col-action")
                with Vertical(id="dictation-model-list", classes="hug-container"):
                    pass  # populated in on_mount

                yield Static("")

                # ── Hotkey ─────────────────────────────────────────────
                hotkey_desc = Static(
                    "  Double-tap to start \u00b7 single tap to stop",
                    id="hotkey-label",
                )
                hotkey_desc.border_title = "Hotkey"
                # Derived from VALID_HOTKEYS so it never drifts out of sync
                hotkey_desc.border_subtitle = " / ".join(k for k, _ in _HOTKEY_ITEMS)
                with Horizontal(classes="top-container"):
                    yield hotkey_desc

                current_hotkey_display = VALID_HOTKEYS.get(current_hotkey, current_hotkey)
                yield Static(
                    f"  Currently selected: {current_hotkey_display}   \u00b7   click a key below to change",
                    id="hotkey-current-label",
                    classes="help-text",
                )
                yield Static("")
                with Horizontal(id="hotkey-row", classes="hug-container"):
                    for key_id, key_label in _HOTKEY_ITEMS:
                        variant = (
                            "btn-primary" if key_id == current_hotkey else "btn-secondary"
                        )
                        yield Button(
                            key_label,
                            id=f"hotkey-{key_id}",
                            classes=f"btn {variant} btn-inline",
                        )

                yield Static("")

                # ── Sounds ─────────────────────────────────────────────
                sounds_switch = Switch(
                    value=sounds_on, id="sounds-switch", classes="switch-input"
                )
                sounds_switch.border_title = "System sounds"
                sounds_switch.border_subtitle = (
                    "Play macOS sounds on start, stop, and paste"
                )
                with Horizontal(classes="top-container"):
                    yield sounds_switch

                yield Static("")

                # ── Auto-enter ─────────────────────────────────────────
                auto_enter_switch = Switch(
                    value=auto_enter_on, id="auto-enter-switch", classes="switch-input"
                )
                auto_enter_switch.border_title = "Auto-enter after paste"
                auto_enter_switch.border_subtitle = (
                    "Press Return after pasting — great for chats; turn off for documents"
                )
                with Horizontal(classes="top-container"):
                    yield auto_enter_switch

                yield Static("")

                # ── Usage note ─────────────────────────────────────────
                usage_note = Static(
                    f"  Run [bold]{alias} dictate[/bold] in a terminal to start the dictation daemon.",
                    id="dictation-usage-note",
                )
                usage_note.border_title = "How to use dictation"
                with Horizontal(classes="top-container"):
                    yield usage_note

                yield Static("")

            with Horizontal(classes="footer-container"):
                yield Static("", classes="spacer-x")
                yield Button(
                    "Back", id="btn-back", classes="btn btn-secondary btn-inline fixed-width"
                )

    def on_mount(self) -> None:
        self._refresh_models()

    def _refresh_models(self) -> None:
        cfg = load_config()
        current = cfg.get("dictation_model", "base")
        container = self.query_one("#dictation-model-list", Vertical)
        container.remove_children()

        for name in WHISPER_MODEL_ORDER:
            installed = is_model_available(name)
            is_current = name == current
            mark = "\u2713" if installed else "\u2718"
            heart = " \u2665\ufe0e" if is_current else ""

            if installed:
                name_ctrl: Static | Button = Button(
                    f"{name}{heart}",
                    id=f"dict-set-{name}",
                    classes="btn btn-secondary btn-inline model-col-model",
                )
            else:
                name_ctrl = Static(name, classes="model-col-model model-name-static")

            row = Horizontal(
                Static(mark, classes="model-col-mark"),
                name_ctrl,
                Static(
                    "installed" if installed else "not installed",
                    classes="model-col-action",
                ),
                classes="strip",
            )
            container.mount(row)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Auto-save toggle changes."""
        sid = event.switch.id
        if sid == "sounds-switch":
            cfg = load_config()
            cfg["dictation_sounds"] = bool(event.value)
            save_config(cfg)
            self.notify(f"Sounds {'on' if event.value else 'off'}.")
        elif sid == "auto-enter-switch":
            cfg = load_config()
            cfg["dictation_auto_enter"] = bool(event.value)
            save_config(cfg)
            self.notify(f"Auto-enter {'on' if event.value else 'off'}.")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id

        if bid == "btn-back":
            self.action_back()
            return

        # Model selection — save immediately
        if bid and bid.startswith("dict-set-"):
            model = bid.replace("dict-set-", "")
            if not is_model_available(model):
                self.notify(f"Model {model} is not installed.", severity="error")
                return
            cfg = load_config()
            cfg["dictation_model"] = model
            save_config(cfg)
            self.notify(f"Dictation model set to {model}.")
            self._refresh_models()
            return

        # Hotkey selection — save immediately
        if bid and bid.startswith("hotkey-"):
            hotkey = bid.replace("hotkey-", "")
            if hotkey not in VALID_HOTKEYS:
                logger.warning("Unknown hotkey id pressed: %r", hotkey)
                return
            cfg = load_config()
            cfg["dictation_hotkey"] = hotkey
            save_config(cfg)
            self.notify(f"Hotkey set to {VALID_HOTKEYS[hotkey]}.")
            self._update_hotkey_buttons(hotkey)
            return

    def _update_hotkey_buttons(self, active_hotkey: str) -> None:
        """Update button styles and current-label to reflect the newly selected hotkey."""
        display = VALID_HOTKEYS.get(active_hotkey, active_hotkey)
        try:
            self.query_one("#hotkey-current-label", Static).update(
                f"  Currently selected: {display}   \u00b7   click a key below to change"
            )
        except Exception:
            pass
        for key_id, _ in _HOTKEY_ITEMS:
            try:
                btn = self.query_one(f"#hotkey-{key_id}", Button)
            except Exception as exc:
                logger.debug("Could not find hotkey button %r: %s", key_id, exc)
                continue
            if key_id == active_hotkey:
                btn.remove_class("btn-secondary")
                btn.add_class("btn-primary")
            else:
                btn.remove_class("btn-primary")
                btn.add_class("btn-secondary")
