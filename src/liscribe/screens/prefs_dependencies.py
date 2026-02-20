"""Preferences — Dependency check with install/remove actions."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widgets import Button, Static

from liscribe.screens.top_bar import TopBar
from liscribe.platform_setup import (
    get_install_command,
    get_remove_command,
    run_all_checks,
    run_install,
    run_remove,
)
from liscribe.screens.base import BackScreen


class PrefsDependenciesScreen(BackScreen):
    """Show dependency check results; install/remove buttons where supported."""

    def compose(self):
        with Vertical(classes="screen-frame"):
            yield TopBar(variant="compact", section="Dependencies")
            with Vertical(classes="screen-body"):
                yield Static("", classes="spacer")
                with ScrollableContainer(id="deps-container", classes="scroll-fill"):
                    pass  # filled in on_mount
                yield Static("", classes="margin-small")
            with Horizontal(classes="screen-body-footer"):
                yield Button("^c Back to Preferences", id="btn-back", classes="btn secondary inline hug-row")
                yield Static("", classes="spacer-row")

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
                    Button("Download", id=f"install-{name}", classes="btn primary inline"),
                )
            elif ok and get_remove_command(name):
                row = Horizontal(
                    Static(line, shrink=True),
                    Button("Remove", id=f"remove-{name}", classes="btn danger inline"),
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
            return
        if event.button.id and event.button.id.startswith("remove-"):
            check_name = event.button.id.replace("remove-", "")
            self.run_worker(
                self._run_remove,
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

    def _run_remove(self, check_name: str) -> None:
        success, out = run_remove(check_name)

        def done():
            if success:
                self.notify(f"Removed {check_name}. Restart terminal or app if needed.")
            else:
                self.notify(f"Remove failed: {out[:100]}", severity="error")
            self._refresh()

        self.app.call_from_thread(done)
