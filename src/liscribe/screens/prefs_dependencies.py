"""Preferences — Dependency check with Install button."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Button, Static

from liscribe.platform_setup import get_install_command, run_all_checks, run_install
from liscribe.screens.base import BackScreen


class PrefsDependenciesScreen(BackScreen):
    """Show dependency check results; Install button for missing items."""

    def compose(self):
        with Vertical(classes="screen-frame"):
            with Horizontal(classes="top-bar compact"):
                yield Static("liscribe", classes="brand")
                yield Static("Dependency check", classes="top-bar-section")
            with Vertical(classes="screen-body"):
                with ScrollableContainer(id="deps-container", classes="scroll-fill"):
                    pass  # filled in on_mount
                yield Button("Back to Preferences", id="btn-back", classes="btn secondary")

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        container = self.query_one("#deps-container", ScrollableContainer)
        container.remove_children()
        results = run_all_checks(include_speaker=True)
        for name, ok, msg in results:
            status = "OK" if ok else "MISSING"
            short = msg.split("\n")[0] if msg else ""
            line = f"{name:<22} {status:<8} {short}"
            if not ok and get_install_command(name):
                row = Horizontal(
                    Static(line, shrink=True),
                    Button("Install", id=f"install-{name}", classes="btn primary inline"),
                )
            else:
                row = Horizontal(Static(line, shrink=True))
            container.mount(row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.action_back()
            return
        if event.button.id and event.button.id.startswith("install-"):
            check_name = event.button.id.replace("install-", "")
            self.run_worker(
                self._run_install,
                check_name,
                exclusive=True,
                thread=True,
            )

    def _run_install(self, check_name: str) -> None:
        success, out = run_install(check_name)
        def done():
            if success:
                self.notify(f"Installed {check_name}. Restart terminal or app if needed.")
            else:
                self.notify(f"Install failed: {out[:100]}", severity="error")
            self._refresh()
        self.app.call_from_thread(done)
