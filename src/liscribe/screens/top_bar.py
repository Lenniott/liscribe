from __future__ import annotations

from typing import Literal

from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.reactive import reactive
from textual.widgets import Static
from textual.app import ComposeResult

from liscribe.screens.base import __version__, render_brand


# Terminal height below which we show compact instead of hero
COMPACT_BELOW_LINES = 20
# Terminal width below which we show compact instead of hero
COMPACT_BELOW_COLUMNS = 22


class TopBar(Vertical):
    """Top bar container: hero or compact with optional inline child widgets."""

    status_text = reactive("")
    _compact = reactive(True, layout=True)

    DEFAULT_CSS = """
    TopBar {
        width: 100%;
        padding: 0;
        background: $surface;
        color: $accent;
        align: center top;
        height: 11;
    }

    TopBar.compact {
        height: 1;
    }

    /* Hero/compact mode toggling */
    TopBar .top-bar-hero {
        width: 100%;
        height: auto;
    }

    TopBar .top-bar-compact-row {
        width: 100%;
        height: 1;
        align: left middle;
        display: none;
    }
    TopBar.compact .top-bar-hero {
        display: none;
    }
    TopBar.compact .top-bar-compact-row {
        display: block;
    }

    /* Inline slot for dynamic content */
    TopBar .top-bar-inline-slot,
    TopBar .top-bar-inline-slot > *,
    TopBar #top-bar-inline-status,
    TopBar #status-text {
        width: auto;
        min-width: 0;
    }
    TopBar .top-bar-inline-slot {
        height: 1;
        align: left middle;
        background: $accent;
    }

    TopBar .container { height: auto; }

    TopBar .logo {
        width: auto;
        align: center middle;
        text-align: center;
        color: $accent;
        text-style: bold;
        margin-right: 0;
    }

    TopBar .subtitle {
        width: 100%;
        align: center middle;
        text-align: center;
        color: $text;
        height: 1;
    }

    TopBar .version {
        width: 100%;
        align: right middle;
        text-align: right;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        variant: Literal["hero", "compact"] = "compact",
        section: str = "",
        *,
        compact_below_lines: int | str | None = COMPACT_BELOW_LINES,
        compact_below_columns: int | str | None = COMPACT_BELOW_COLUMNS,
    ) -> None:
        self._variant = variant
        self._section = section
        self._compact_below_lines = self._coerce_threshold(compact_below_lines)
        self._compact_below_columns = self._coerce_threshold(compact_below_columns)
        self._last_app_height: int | None = None
        self._last_app_width: int | None = None
        super().__init__(classes="top-bar")

    @staticmethod
    def _coerce_threshold(value: int | str | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text or text.lower() == "none":
                return None
            try:
                return int(text)
            except ValueError:
                return None
        return None

    def _should_compact_for(self, width: int, height: int) -> bool:
        """Check if we should use compact mode for given layout dimensions."""
        if self._variant != "hero":
            return True
        if self._compact_below_lines is not None and height < self._compact_below_lines:
            return True
        if self._compact_below_columns is not None and width < self._compact_below_columns:
            return True
        return False

    def on_mount(self) -> None:
        self.app.call_after_refresh(self._initialize_top_bar)
        self.set_interval(0.2, self._refresh_compact_state)

    def on_resize(self, event: Resize) -> None:
        # Use local widget width and screen height for a consistent compact calculation.
        try:
            width = event.size.width
            height = self.screen.size.height
            self._refresh_compact_state_with(width, height)
        except Exception:
            self.app.call_after_refresh(self._refresh_compact_state)

    def _initialize_top_bar(self) -> None:
        self._adopt_inline_children()
        self._refresh_compact_state()
        self.watch_status_text()

    def _refresh_compact_state(self) -> None:
        """Refresh mode when terminal height or width changes, even if this widget didn't resize."""
        try:
            screen_size = self.screen.size
            width = self.size.width or screen_size.width
            self._refresh_compact_state_with(width, screen_size.height)
        except Exception:
            return

    def _refresh_compact_state_with(self, width: int, height: int) -> None:
        """Refresh compact/hero based on given width and height."""
        if height == self._last_app_height and width == self._last_app_width:
            return
        self._last_app_height = height
        self._last_app_width = width
        self._update_state()

    def _update_state(self) -> None:
        w = self._last_app_width if self._last_app_width is not None else 0
        h = self._last_app_height if self._last_app_height is not None else 0
        self._compact = self._should_compact_for(w, h)
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
            yield Static(f"v{__version__}", classes="version")
            with Horizontal( classes="container"):
                yield Static("", classes="spacer-x")
                yield Static(render_brand(), classes="logo")
                yield Static("", classes="spacer-x")
            yield Static("")
            yield Static(
                "It listens & transcribes locally",
                classes="subtitle",
            )
        with Horizontal(classes="top-bar-compact-row top-bar-internal"):
            yield Static("liscribe", classes="brand top-bar-internal")
            with Horizontal(
                id="top-bar-inline-slot",
                classes="top-bar-inline-slot top-bar-internal",
            ):
                yield Static("", id="top-bar-inline-status", classes="top-bar-internal")
            yield Static("", classes="spacer-x top-bar-internal")
            yield Static(self._section or "", classes="top-bar-section top-bar-internal")
