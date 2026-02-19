"""Modal screens used by Recording (mic select, cancel confirm)."""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from liscribe.recorder import list_input_devices


class MicSelectScreen(ModalScreen[int | None]):
    """Modal screen to select a different microphone."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, current_device: int | None) -> None:
        super().__init__()
        self.current_device = current_device

    def compose(self):
        devices = list_input_devices()
        options = []
        for dev in devices:
            marker = " ◄" if dev["index"] == self.current_device else ""
            label = f"[{dev['index']}] {dev['name']} ({dev['channels']}ch, {dev['sample_rate']}Hz){marker}"
            options.append(Option(label, id=str(dev["index"])))

        yield Vertical(
            Label("Select microphone:", id="mic-select-title"),
            OptionList(*options, id="mic-list"),
            id="mic-select-container",
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(int(event.option.id))

    def action_cancel(self) -> None:
        self.dismiss(None)


class ConfirmCancelScreen(ModalScreen[bool]):
    """Ask user to confirm discarding the recording."""

    BINDINGS = [
        Binding("escape", "no", "No"),
        Binding("y", "yes", "Yes"),
        Binding("n", "no", "No"),
    ]

    def compose(self):
        yield Vertical(
            Label("Discard recording? Unsaved audio will be lost.", id="cancel-confirm-message"),
            OptionList(
                Option("Yes, discard recording", id="yes"),
                Option("No, keep recording", id="no"),
                id="cancel-confirm-list",
            ),
            id="cancel-confirm-container",
        )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id == "yes":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)
