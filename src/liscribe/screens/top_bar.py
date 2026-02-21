from __future__ import annotations

from typing import Literal

from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.reactive import reactive
from textual.widgets import Static
from textual.app import ComposeResult

from liscribe.screens.base import __version__, render_brand


# Terminal height below which we show compact instead of hero
COMPACT_BELOW_LINES = 28


class TopBar(Vertical):
    """Top bar container: hero or compact with optional inline child widgets."""

    status_text = reactive("")
    _compact = reactive(True, layout=True)

    DEFAULT_CSS = """
    TopBar {
        width: 100%;
        padding: 0 1;
        background: $accent;
        color: $text;
        align: center middle;
        height: 12;
    }
    TopBar.hero {
        margin-bottom: 1;
    }
    TopBar.compact {
        height: 1;
        margin-bottom: 1;
    }
    TopBar > .top-bar-hero {
        width: 100%;
    }
    TopBar > .top-bar-compact-row {
        width: 100%;
        height: 1;
        align: left middle;
        display: none;
    }
    TopBar.compact > .top-bar-hero {
        display: none;
    }
    TopBar.compact > .top-bar-compact-row {
        display: block;
    }
    TopBar.compact > .top-bar-compact-row > .brand {
        width: auto;
    }
    TopBar .top-bar-inline-slot {
        width: auto;
        height: 1;
        align: left middle;
        background: $accent;
    }
    TopBar .top-bar-inline-slot > * {
        width: auto;
        min-width: 0;
    }
    TopBar #top-bar-inline-status {
        width: auto;
        min-width: 0;
    }
    TopBar #status-text {
        width: auto;
        min-width: 0;
    }
    """

    def __init__(
        self,
        variant: Literal["hero", "compact"] = "compact",
        section: str = "",
        *,
        compact_below_lines: int | None = COMPACT_BELOW_LINES,
    ) -> None:
        self._variant = variant
        self._section = section
        self._compact_below_lines = compact_below_lines
        self._last_app_height: int | None = None
        super().__init__(classes="top-bar")

    def _should_compact(self) -> bool:
        """Check if we should use compact mode based on app layout height."""
        if self._variant != "hero":
            return True
        if self._compact_below_lines is None:
            return False
        return self.app.size.height < self._compact_below_lines

    def on_mount(self) -> None:
        self.app.call_after_refresh(self._initialize_top_bar)
        self.set_interval(0.2, self._refresh_compact_state)

    def on_resize(self, event: Resize) -> None:
        self.app.call_after_refresh(self._refresh_compact_state)

    def _initialize_top_bar(self) -> None:
        self._adopt_inline_children()
        self._refresh_compact_state()
        self.watch_status_text()

    def _refresh_compact_state(self) -> None:
        """Refresh mode when terminal height changes, even if this widget didn't resize."""
        try:
            app_height = self.app.size.height
        except Exception:
            return
        if app_height == self._last_app_height:
            return
        self._last_app_height = app_height
        self._update_state()

    def _update_state(self) -> None:
        self._compact = self._should_compact()
        self.remove_class("hero")
        self.remove_class("compact")
        self.add_class("compact" if self._compact else "hero")

    def _adopt_inline_children(self) -> None:
        """Move direct child widgets yielded by parent compose into compact inline slot."""
        try:
            inline_slot = self.query_one("#top-bar-inline-slot", Horizontal)
        except Exception:
            return

        for child in list(self.children):
            if child.has_class("top-bar-internal"):
                continue
            child.remove()
            inline_slot.mount(child)

    def watch_status_text(self) -> None:
        """Update inline status text, preferring a slotted #status-text child if present."""
        target: Static | None = None
        try:
            target = self.query_one("#status-text", Static)
        except Exception:
            try:
                target = self.query_one("#top-bar-inline-status", Static)
            except Exception:
                target = None
        if target is not None:
            target.update(self.status_text or "")

    def compose(self) -> ComposeResult:
        with Vertical(classes="top-bar-hero top-bar-internal"):
            yield Static(f"v{__version__}", classes="version-row top-bar-internal")
            yield Static("")
            yield Static(render_brand(), classes="title-row brand top-bar-internal")
            yield Static("")
            yield Static(
                "It listens & transcribes locally",
                classes="subtitle-row tagline top-bar-internal",
            )
        with Horizontal(classes="top-bar-compact-row top-bar-internal"):
            yield Static("liscribe", classes="brand top-bar-internal")
            with Horizontal(
                id="top-bar-inline-slot",
                classes="top-bar-inline-slot top-bar-internal",
            ):
                yield Static("", id="top-bar-inline-status", classes="top-bar-internal")
            yield Static("", classes="spacer-row top-bar-internal")
            yield Static(self._section or "", classes="top-bar-section top-bar-internal")
