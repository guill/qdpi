"""QDPI TUI Application."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header

from qdpi.config.loader import load_config, ConfigError
from qdpi.core.environment import EnvironmentManager, EnvironmentError
from qdpi.tui.screens.name_input import NameInputScreen
from qdpi.tui.screens.repo_select import RepoSelectScreen
from qdpi.tui.screens.branch_select import BranchSelectScreen
from qdpi.tui.screens.confirmation import ConfirmationScreen


class QdpiApp(App):
    """QDPI TUI Application for creating environments."""

    TITLE = "QDPI - Create Environment"
    CSS = """
    Screen {
        align: center middle;
    }
    
    #main-container {
        width: 80%;
        max-width: 100;
        height: auto;
        max-height: 90%;
        border: solid green;
        padding: 1 2;
    }
    
    .step-indicator {
        text-align: right;
        color: $text-muted;
    }
    
    .title {
        text-style: bold;
        margin-bottom: 1;
    }
    
    .help-text {
        color: $text-muted;
        margin-top: 1;
    }
    
    Input {
        margin: 1 0;
    }
    
    SelectionList {
        height: auto;
        max-height: 15;
        margin: 1 0;
    }
    
    .repo-branch-item {
        margin: 0 0 1 0;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", show=True),
        Binding("escape", "back", "Back", show=True),
    ]

    def __init__(
        self,
        prefilled_name: str | None = None,
    ):
        """
        Initialize the app.

        Args:
            prefilled_name: Pre-filled environment name (optional).
        """
        super().__init__()
        self.prefilled_name = prefilled_name

        # State
        self.env_name: str = prefilled_name or ""
        self.selected_repos: list[str] = []
        self.repo_branches: dict[str, str] = {}

        # Load config
        try:
            self.config = load_config()
            self.manager = EnvironmentManager(self.config)
            self.available_repos = list(self.config.repositories.keys())
        except ConfigError as e:
            self.config = None
            self.manager = None
            self.available_repos = []
            self.config_error = str(e)

    def on_mount(self) -> None:
        """Called when app is mounted."""
        if self.config is None:
            self.notify(f"Configuration error: {self.config_error}", severity="error")
            self.exit(1)
            return

        if not self.available_repos:
            self.notify(
                "No repositories configured. Edit your config.yaml first.", severity="error"
            )
            self.exit(1)
            return

        # Start with name input screen
        self.push_screen(NameInputScreen(self.env_name))

    def action_back(self) -> None:
        """Go back to previous screen, or quit if on first screen."""
        # If we're on the first user screen (NameInputScreen), quit instead of going back
        # to an empty default screen
        if len(self.screen_stack) <= 2:
            # Stack has: default screen + first pushed screen
            self.exit(1)
        else:
            self.pop_screen()

    def action_quit(self) -> None:
        """Quit the application."""
        self.exit(1)

    def on_name_input_screen_submitted(self, event: NameInputScreen.Submitted) -> None:
        """Handle name input submission."""
        self.env_name = event.name
        self.pop_screen()
        self.push_screen(RepoSelectScreen(self.available_repos, self.selected_repos))

    def on_repo_select_screen_submitted(self, event: RepoSelectScreen.Submitted) -> None:
        """Handle repo selection submission."""
        self.selected_repos = event.repos
        self.pop_screen()

        # Initialize branch defaults
        for repo in self.selected_repos:
            if repo not in self.repo_branches:
                self.repo_branches[repo] = "main"

        self.push_screen(
            BranchSelectScreen(
                self.config,
                self.selected_repos,
                self.repo_branches,
            )
        )

    def on_branch_select_screen_submitted(self, event: BranchSelectScreen.Submitted) -> None:
        """Handle branch selection submission."""
        self.repo_branches = event.branches
        self.pop_screen()
        self.push_screen(
            ConfirmationScreen(
                self.env_name,
                self.repo_branches,
                self.config,
            )
        )

    def on_confirmation_screen_confirmed(self, event: ConfirmationScreen.Confirmed) -> None:
        """Handle confirmation - create the environment."""
        if self.manager is None:
            self.notify("Manager not initialized", severity="error")
            return

        try:

            def on_branch_not_found(
                repo_name: str,
                branch: str,
                available: list[str],
            ) -> str | None:
                # In TUI, we should have validated branches already
                # but just in case, use main as fallback
                return "main" if "main" in available else (available[0] if available else None)

            env = self.manager.create(
                name=self.env_name,
                repo_branches=self.repo_branches,
                on_branch_not_found=on_branch_not_found,
            )
            self.notify(f"Environment created: {env.path}", severity="information")
            self.exit(0)

        except EnvironmentError as e:
            self.notify(f"Failed to create environment: {e}", severity="error")


def run_tui(prefilled_name: str | None = None) -> None:
    """Run the TUI application."""
    app = QdpiApp(prefilled_name)
    app.run()
