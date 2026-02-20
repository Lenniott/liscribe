"""Preferences — Whisper: language, default model, download/remove models."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from liscribe.config import load_config, save_config
from liscribe.screens.base import BackScreen
from liscribe.transcriber import is_model_available, load_model, remove_model

WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]


class PrefsWhisperScreen(BackScreen):
    """Language, default model, download/remove models."""

    def compose(self):
        cfg = load_config()
        with Vertical(classes="screen-frame"):
            with Horizontal(classes="top-bar compact"):
                yield Static("liscribe", classes="brand")
                yield Static("whisper", classes="top-bar-section")
            with Vertical(classes="screen-body"):
                yield Static("", classes="spacer")
                with Vertical(classes="prefs-language-row"):
                    yield Static("Language (e.g. en, fr, auto):")
                    yield Input(
                        value=cfg.get("language", "en") or "en",
                        id="language-input",
                    )
                yield Static("Models:")
                yield Static("", classes="margin-small")
                with Horizontal(classes="model-row model-header-row"):
                    yield Static("", classes="model-col-mark")
                    yield Static("Model", classes="model-col-model")
                    yield Static("Action", classes="model-col-action")
                with Vertical(id="model-list"):
                    pass
                yield Static("", classes="margin-small")
            with Horizontal(classes="screen-body-footer"):
                yield Button("^c Back to preferences", id="btn-back", classes="btn secondary inline hug-row")
                yield Static("", classes="spacer-row")
                yield Button("Save", id="btn-save-lang", classes="btn primary inline hug-row")


    def on_mount(self) -> None:
        self._refresh_models()

    def _refresh_models(self) -> None:
        cfg = load_config()
        container = self.query_one("#model-list", Vertical)
        container.remove_children()
        for name in WHISPER_MODELS:
            installed = is_model_available(name)
            current = name == cfg.get("whisper_model")
            downloaded_mark = "✓" if installed else "✘"
            default_mark = " ♥︎" if current else ""

            row = Horizontal(
                Static(downloaded_mark, classes="model-col-mark"),
                Button(f"{name}{default_mark}", id=f"set-{name}", classes="btn secondary inline model-col-model"),
                Button(
                    "Remove" if installed else "Download",
                    id=f"{'remove' if installed else 'download'}-{name}",
                    classes="btn secondary inline model-col-action",
                ),
                classes="model-row",
            )
            container.mount(row)

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
        if event.button.id and event.button.id.startswith("set-"):
            model = event.button.id.replace("set-", "")
            cfg = load_config()
            cfg["whisper_model"] = model
            save_config(cfg)
            self.notify(f"Default model set to {model}")
            self._refresh_models()
            return
        if event.button.id and event.button.id.startswith("download-"):
            model = event.button.id.replace("download-", "")
            self.run_worker(self._download_model, model, exclusive=True, thread=True)
            return
        if event.button.id and event.button.id.startswith("remove-"):
            model = event.button.id.replace("remove-", "")
            self.run_worker(self._remove_model, model, exclusive=True, thread=True)

    def _download_model(self, model: str) -> None:
        try:
            load_model(model)
            error = None
        except Exception as exc:
            error = str(exc)

        def done() -> None:
            if error:
                self.notify(f"Download failed ({model}): {error}", severity="error")
            else:
                self.notify(f"Model ready: {model}")
            self._refresh_models()

        self.app.call_from_thread(done)

    def _remove_model(self, model: str) -> None:
        ok, msg = remove_model(model)

        def done() -> None:
            if ok:
                self.notify(f"Removed model: {model}")
            else:
                self.notify(msg, severity="error")
            self._refresh_models()

        self.app.call_from_thread(done)
