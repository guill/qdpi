"""Confirmation screen for QDPI TUI."""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Label, Static

from qdpi.config.models import Config
from qdpi.core.template import TemplateEngine


class ConfirmationScreen(Screen):
    """Screen for confirming environment creation."""

    BINDINGS = [
        ("enter", "confirm", "Create"),
    ]

    class Confirmed(Message):
        """Sent when creation is confirmed."""

        pass

    def __init__(
        self,
        name: str,
        repo_branches: dict[str, str],
        config: Config,
    ) -> None:
        super().__init__()
        self.env_name = name
        self.repo_branches = repo_branches
        self.config = config

    def compose(self) -> ComposeResult:
        env_path = self.config.environments_dir / self.env_name
        repo_names = set(self.repo_branches.keys())

        # Determine which templates will be generated
        templates_to_generate = []
        for template in self.config.templates:
            if TemplateEngine.should_render(template, repo_names):
                templates_to_generate.append(template.destination)

        # Determine which symlinks will be created
        symlinks_to_create = []
        for symlink in self.config.symlinks:
            if all(r in repo_names for r in symlink.when):
                symlinks_to_create.append(f"{symlink.target} → {symlink.source}")

        with Container(id="main-container"):
            yield Static("[4/4]", classes="step-indicator")
            yield Label("Review your environment:", classes="title")

            yield Static(f"\n[bold]Name:[/bold] {self.env_name}")
            yield Static(f"[bold]Path:[/bold] {env_path}")

            yield Static("\n[bold]Repositories:[/bold]")
            for repo, branch in self.repo_branches.items():
                yield Static(f"  • {repo} → {branch}")

            if templates_to_generate:
                yield Static("\n[bold]Files to generate:[/bold]")
                for template in templates_to_generate:
                    yield Static(f"  • {template}")

            if symlinks_to_create:
                yield Static("\n[bold]Symlinks:[/bold]")
                for symlink in symlinks_to_create:
                    yield Static(f"  • {symlink}")

            yield Static("\n")
            yield Button("Create Environment", variant="primary", id="create-btn")

    def on_mount(self) -> None:
        """Focus the create button."""
        self.query_one("#create-btn", Button).focus()

    @on(Button.Pressed, "#create-btn")
    def on_create_pressed(self) -> None:
        """Handle create button press."""
        self.post_message(self.Confirmed())

    def action_confirm(self) -> None:
        """Handle enter key."""
        self.post_message(self.Confirmed())
