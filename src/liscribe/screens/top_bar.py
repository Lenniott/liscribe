"""Reusable top bar: hero (version + brand + tagline) or compact (brand + section). Toggles by terminal height via render()."""

from __future__ import annotations

from typing import Literal

from rich.console import Group
from rich.text import Text
from textual.widgets import Static
from textual.reactive import reactive
from textual.events import Resize
from textual.app import RenderResult

from liscribe.screens.base import __version__, render_brand


# Terminal height below which we show compact instead of hero
COMPACT_BELOW_LINES = 28


class TopBar(Static):
    """One component, two states: hero or compact. Uses render() + reactive so Textual refreshes on resize."""

    DEFAULT_CSS = """
    TopBar {
        width: 100%;
        height: auto;
        padding: 0 1;
        background: $accent;
        color: $text;
        align: center middle;
    }
    TopBar.hero {
        height: auto;
        margin-bottom: 1;
    }
    TopBar.compact {
        height: 1;
        margin-bottom: 1;
    }
    """

    # When True, show compact (one line); when False, show hero. Updated on mount and resize.
    _compact = reactive(True)

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
        super().__init__(classes="top-bar")

    def _should_compact(self) -> bool:
        if self._variant != "hero":
            return True
        if self._compact_below_lines is None:
            return False
        try:
            h = self.app.terminal_size.height
        except Exception:
            return False
        return h < self._compact_below_lines

    def on_mount(self) -> None:
        self._compact = self._should_compact()
        self._update_classes()

    def on_resize(self, event: Resize) -> None:
        # Use terminal size to decide state; update reactive so render() runs again
        self._compact = self._should_compact()
        self._update_classes()

    def _update_classes(self) -> None:
        self.remove_class("hero")
        self.remove_class("compact")
        self.add_class("compact" if self._compact else "hero")

    def render(self) -> RenderResult:
        if self._compact:
            return self._render_compact()
        return self._render_hero()

    def _render_compact(self) -> RenderResult:
        # One line: "liscribe" left, section right (Rich will align if we use a single line)
        line = Text()
        line.append("liscribe", style="bold")
        line.append("  ")
        line.append(self._section or "", style="dim")
        return line

    def _render_hero(self) -> RenderResult:
        version = Text(f"v{__version__}")
        brand = Text(render_brand(), style="bold")
        tagline = Text("It listens & transcribes locally", style="dim")
        return Group(version, brand, tagline)
