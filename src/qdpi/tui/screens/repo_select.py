"""Repository selection screen for QDPI TUI."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Label, SelectionList, Static
from textual.widgets.selection_list import Selection


class RepoSelectScreen(Screen):
    """Screen for selecting repositories."""

    BINDINGS = [
        ("ctrl+n", "submit", "Continue"),
    ]

    class Submitted(Message):
        """Sent when selection is submitted."""

        def __init__(self, repos: list[str]) -> None:
            self.repos = repos
            super().__init__()

    def __init__(self, available_repos: list[str], preselected: list[str] | None = None) -> None:
        super().__init__()
        self.available_repos = available_repos
        self.preselected = set(preselected or [])

    def compose(self) -> ComposeResult:
        selections = [
            Selection(repo, repo, repo in self.preselected) for repo in self.available_repos
        ]

        yield Container(
            Static("[2/4]", classes="step-indicator"),
            Label("Select repositories to include:", classes="title"),
            SelectionList[str](*selections, id="repo-list"),
            Static("", id="selection-count"),
            Static("[Space] Toggle  [Ctrl+N] Continue  [Esc] Back", classes="help-text"),
            Horizontal(
                Button("Continue", variant="primary", id="continue-btn"),
            ),
            id="main-container",
        )

    def on_mount(self) -> None:
        """Focus the selection list on mount."""
        self.query_one("#repo-list", SelectionList).focus()
        self._update_count()

    def _update_count(self) -> None:
        """Update the selection count display."""
        selection_list = self.query_one("#repo-list", SelectionList)
        count = len(selection_list.selected)
        self.query_one("#selection-count", Static).update(f"Selected: {count} repositories")

    @on(SelectionList.SelectedChanged)
    def on_selection_changed(self) -> None:
        """Update count when selection changes."""
        self._update_count()

    @on(Button.Pressed, "#continue-btn")
    def on_continue_pressed(self) -> None:
        """Handle continue button press."""
        self._submit()

    def action_submit(self) -> None:
        """Submit the selection."""
        self._submit()

    def _submit(self) -> None:
        """Submit the selection."""
        selection_list = self.query_one("#repo-list", SelectionList)
        selected = list(selection_list.selected)

        if not selected:
            self.notify("Please select at least one repository", severity="warning")
            return

        self.post_message(self.Submitted(selected))
