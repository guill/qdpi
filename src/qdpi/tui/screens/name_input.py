"""Name input screen for QDPI TUI."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Input, Label, Static

from qdpi.utils.paths import is_valid_environment_name


class NameInputScreen(Screen):
    """Screen for entering environment name."""

    class Submitted(Message):
        """Sent when name is submitted."""

        def __init__(self, name: str) -> None:
            self.name = name
            super().__init__()

    def __init__(self, prefilled: str = "") -> None:
        super().__init__()
        self.prefilled = prefilled

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[1/4]", classes="step-indicator"),
            Label("Environment Name:", classes="title"),
            Input(
                value=self.prefilled,
                placeholder="my-feature-branch",
                id="name-input",
            ),
            Static(
                "Name must be a valid directory name (letters, numbers, hyphens, underscores).",
                classes="help-text",
            ),
            id="main-container",
        )

    def on_mount(self) -> None:
        """Focus the input on mount."""
        self.query_one("#name-input", Input).focus()

    @on(Input.Submitted, "#name-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        name = event.value.strip()

        if not name:
            self.notify("Please enter an environment name", severity="warning")
            return

        if not is_valid_environment_name(name):
            self.notify(
                "Invalid name. Use only letters, numbers, hyphens, and underscores.",
                severity="error",
            )
            return

        self.post_message(self.Submitted(name))
