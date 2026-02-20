"""Reusable top bar: hero (version + brand + tagline) or compact (brand + section), responsive to terminal height."""

from __future__ import annotations

from typing import Literal

from textual.containers import Horizontal, Vertical
from textual.widgets import Static
from textual.events import Resize

from liscribe.screens.base import __version__, render_brand


# Terminal height below which we show compact instead of hero (so both states are usable)
COMPACT_BELOW_LINES = 28


class TopBar(Vertical):
    """One component, two states: hero (version + brand + tagline) or compact (brand + section). Toggles by terminal height."""

    DEFAULT_CSS = """
    TopBar {
        width: 100%;
        height: auto;
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
        self._last_effective: Literal["hero", "compact"] | None = None
        super().__init__(classes="top-bar-wrapper")

    def _effective_variant(self) -> Literal["hero", "compact"]:
        if self._variant != "hero":
            return "compact"
        if self._compact_below_lines is None:
            return "hero"
        try:
            height = self.app.terminal_size.height
        except Exception:
            return "hero"
        if height < self._compact_below_lines:
            return "compact"
        return "hero"

    def compose(self):
        yield Vertical(id="top-bar-inner")

    def on_mount(self) -> None:
        self._apply_state()

    def on_resize(self, _: Resize) -> None:
        self._apply_state()

    def _apply_state(self) -> None:
        """Switch to hero or compact only when the effective state changes."""
        effective = self._effective_variant()
        if effective == self._last_effective:
            return
        self._last_effective = effective
        self._refresh_content(effective)

    def _refresh_content(self, effective: Literal["hero", "compact"]) -> None:
        inner = self.query_one("#top-bar-inner", Vertical)
        inner.remove_children()
        inner.remove_class("hero")
        inner.remove_class("compact")
        inner.remove_class("top-bar")

        if effective == "hero":
            inner.add_class("top-bar")
            inner.add_class("hero")
            row = Horizontal(classes="row")
            inner.mount(row)
            row.mount(Static(f"v{__version__}", classes="version home-version"))
            inner.mount(Static(render_brand(), classes="brand home-brand"))
            inner.mount(Static("It listens & transcribes locally", classes="tagline"))
        else:
            # compact: single row
            bar = Horizontal(classes="top-bar compact")
            inner.mount(bar)
            bar.mount(
                Static("liscribe", classes="brand"),
                Static(self._section or "", classes="top-bar-section"),
            )
