"""Branch selection screen for QDPI TUI."""

from pathlib import Path  # noqa: F401

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from qdpi.config.models import Config
from qdpi.core.git import GitOperations


class BranchSelectScreen(Screen[None]):
    """Screen for selecting branches for each repository."""

    BINDINGS = [
        ("ctrl+n", "submit", "Continue"),
        ("tab", "next_repo", "Next Repo"),
    ]

    class Submitted(Message):
        """Sent when branches are confirmed."""

        def __init__(self, branches: dict[str, str]) -> None:
            self.branches = branches
            super().__init__()

    def __init__(
        self,
        config: Config,
        repos: list[str],
        initial_branches: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.repos = repos
        self.branches = dict(initial_branches or {})
        self.current_repo_index = 0
        self.repo_branch_lists: dict[str, list[str]] = {}
        self.loading_repos: set[str] = set()

    def compose(self) -> ComposeResult:
        with Container(id="main-container"):
            yield Static("[3/4]", classes="step-indicator")
            yield Label("Select branch for each repository:", classes="title")

            with Vertical(id="branch-selectors"):
                for repo in self.repos:
                    default_branch = self.branches.get(repo, "main")
                    with Container(classes="repo-branch-item", id=f"repo-{repo}"):
                        yield Label(f"{repo}:")
                        yield Input(
                            value=default_branch,
                            placeholder="branch name",
                            id=f"branch-input-{repo}",
                        )
                        yield OptionList(id=f"branch-list-{repo}")

            yield Static("", id="status-text", classes="help-text")
            yield Static("[Tab] Next Repo  [Ctrl+N] Continue  [Esc] Back", classes="help-text")
            yield Horizontal(
                Button("Continue", variant="primary", id="continue-btn"),
            )

    def on_mount(self) -> None:
        """Start fetching branches for all repos."""
        for repo in self.repos:
            self.loading_repos.add(repo)
            self._fetch_branches(repo)

        # Focus first input
        if self.repos:
            first_input = self.query_one(f"#branch-input-{self.repos[0]}", Input)
            first_input.focus()

        self._update_status()

    def _update_status(self) -> None:
        """Update the status text."""
        if self.loading_repos:
            status = f"Fetching branches for: {', '.join(self.loading_repos)}..."
        else:
            status = "All branches loaded."
        self.query_one("#status-text", Static).update(status)

    @work(exclusive=True, group="fetch-branches")
    async def _fetch_branches(self, repo: str) -> None:
        """Fetch branches for a repository in the background."""
        base_repo = self.config.base_repos_dir / repo

        if not base_repo.exists():
            # Repository not cloned yet - we'll use a placeholder
            self.loading_repos.discard(repo)
            self._update_status()
            return

        try:
            branches = await GitOperations.fetch_branches_async(base_repo)
            self.repo_branch_lists[repo] = branches

            # Update the option list
            option_list = self.query_one(f"#branch-list-{repo}", OptionList)
            option_list.clear_options()
            for branch in branches[:20]:  # Limit to 20 branches for performance
                option_list.add_option(Option(branch, id=branch))

        except Exception:
            # Non-fatal - user can still type branch name
            pass
        finally:
            self.loading_repos.discard(repo)
            self._update_status()

    @on(OptionList.OptionSelected)
    def on_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle branch selection from list."""
        # Find which repo this belongs to
        option_list_id = event.option_list.id
        if option_list_id and option_list_id.startswith("branch-list-"):
            repo = option_list_id.replace("branch-list-", "")
            branch = str(event.option.id)

            # Update the input
            input_widget = self.query_one(f"#branch-input-{repo}", Input)
            input_widget.value = branch
            self.branches[repo] = branch

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle manual branch input."""
        input_id = event.input.id
        if input_id and input_id.startswith("branch-input-"):
            repo = input_id.replace("branch-input-", "")
            self.branches[repo] = event.value

            # Filter option list if available
            if repo in self.repo_branch_lists:
                option_list = self.query_one(f"#branch-list-{repo}", OptionList)
                option_list.clear_options()
                query = event.value.lower()
                for branch in self.repo_branch_lists[repo]:
                    if query in branch.lower():
                        option_list.add_option(Option(branch, id=branch))

    def action_next_repo(self) -> None:
        """Move focus to next repository input."""
        self.current_repo_index = (self.current_repo_index + 1) % len(self.repos)
        repo = self.repos[self.current_repo_index]
        self.query_one(f"#branch-input-{repo}", Input).focus()

    @on(Button.Pressed, "#continue-btn")
    def on_continue_pressed(self) -> None:
        """Handle continue button press."""
        self._submit()

    def action_submit(self) -> None:
        """Submit the branch selections."""
        self._submit()

    def _submit(self) -> None:
        """Submit the branch selections."""
        # Collect all branch values from inputs
        for repo in self.repos:
            input_widget = self.query_one(f"#branch-input-{repo}", Input)
            branch = input_widget.value.strip()
            if not branch:
                self.notify(f"Please enter a branch for {repo}", severity="warning")
                return
            self.branches[repo] = branch

        self.post_message(self.Submitted(self.branches))
