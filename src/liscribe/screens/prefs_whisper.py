"""Preferences — Whisper: language, default model, download/remove models."""

from __future__ import annotations

from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import Button, Input, Static

from liscribe.config import load_config, save_config
from liscribe.screens.base import BackScreen
from liscribe.transcriber import is_model_available

WHISPER_MODELS = [
    ("tiny", "~75 MB,  fastest"),
    ("base", "~150 MB, good balance"),
    ("small", "~500 MB, higher accuracy"),
    ("medium", "~1.5 GB, near-best"),
    ("large", "~3 GB,   best accuracy"),
]


class PrefsWhisperScreen(BackScreen):
    """Language, default model, download models."""

    def compose(self):
        cfg = load_config()
        with Vertical(classes="screen-frame"):
            with Horizontal(classes="top-bar compact"):
                yield Static("liscribe", classes="brand")
                yield Static("Whisper", classes="top-bar-section")
            with Vertical(classes="screen-body"):
                yield Static("Language (e.g. en, fr, auto):")
                yield Input(value=cfg.get("language", "en") or "en", id="language-input")
                yield Static("Default model:")
                with ScrollableContainer(id="model-list", classes="scroll-fill"):
                    for name, desc in WHISPER_MODELS:
                        installed = " ✓" if is_model_available(name) else ""
                        current = " (default)" if name == cfg.get("whisper_model") else ""
                        yield Button(
                            f"{name}  {desc}{installed}{current}",
                            id=f"model-{name}",
                            classes="btn secondary",
                        )
                yield Static("Download: run in terminal or use rec setup", classes="screen-body-subtitle")
                yield Button("Save language", id="btn-save-lang", classes="btn primary")
                yield Button("Back to Preferences", id="btn-back", classes="btn secondary")

    def on_mount(self) -> None:
        self._refresh_models()

    def _refresh_models(self) -> None:
        cfg = load_config()
        try:
            container = self.query_one("#model-list", ScrollableContainer)
            container.remove_children()
            for name, desc in WHISPER_MODELS:
                installed = " ✓" if is_model_available(name) else ""
                current = " (default)" if name == cfg.get("whisper_model") else ""
                container.mount(
                    Button(
                        f"{name}  {desc}{installed}{current}",
                        id=f"model-{name}",
                        classes="btn secondary",
                    )
                )
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
            return
        if event.button.id == "btn-save-lang":
            try:
                lang_inp = self.query_one("#language-input", Input)
                cfg = load_config()
                cfg["language"] = lang_inp.value.strip() or "en"
                save_config(cfg)
                self.notify("Language saved")
            except Exception:
                pass
            return
        if event.button.id and event.button.id.startswith("model-"):
            model = event.button.id.replace("model-", "")
            cfg = load_config()
            cfg["whisper_model"] = model
            save_config(cfg)
            self.notify(f"Default model set to {model}")
            self._refresh_models()
