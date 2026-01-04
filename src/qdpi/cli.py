"""QDPI CLI - Quick Development PIpeline."""

import json
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from qdpi.config.loader import (
    GLOBAL_CONFIG_PATH,
    ConfigError,
    init_config,
    load_config,
)
from qdpi.config.models import Config
from qdpi.core.environment import EnvironmentError, EnvironmentManager
from qdpi.core.git import GitOperations  # noqa: F401
from qdpi.registry.registry import PRInfo
from qdpi.utils.github import (
    GitHubError,
    GitHubOperations,
    parse_github_repo,
    parse_pr_reference,
)

app = typer.Typer(
    name="qdpi",
    help="Quick Development PIpeline - Manage multi-repository development environments.",
    no_args_is_help=True,
)

console = Console()
error_console = Console(stderr=True)


def handle_error(message: str, exit_code: int = 1) -> NoReturn:
    """Print error message and exit."""
    error_console.print(f"[red]Error:[/red] {message}")
    raise typer.Exit(exit_code)


def get_manager() -> EnvironmentManager:
    """Get an EnvironmentManager with loaded config."""
    try:
        config = load_config()
        return EnvironmentManager(config)
    except ConfigError as e:
        handle_error(str(e))
        raise  # Never reached, but satisfies type checker


@app.command()
def init(
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing config file"),
    ] = False,
) -> None:
    """Initialize qdpi with a default configuration file."""
    try:
        path = init_config(force=force)
        console.print(f"[green]Created configuration file:[/green] {path}")
        console.print("\nEdit the config to add your repositories:")
        console.print(f"  $EDITOR {path}")
        console.print("\nOptionally add templates to:")
        console.print(f"  {path.parent / 'templates/'}")
    except ConfigError as e:
        handle_error(str(e))


@app.command()
def create(
    name: Annotated[
        str | None,
        typer.Argument(help="Environment name"),
    ] = None,
    repos: Annotated[
        list[str] | None,
        typer.Option(
            "--repo",
            "-r",
            help="Add repository with branch (format: REPO:BRANCH)",
        ),
    ] = None,
    no_fetch: Annotated[
        bool,
        typer.Option("--no-fetch", help="Skip fetching latest from remotes"),
    ] = False,
    no_templates: Annotated[
        bool,
        typer.Option("--no-templates", help="Skip template generation"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompts"),
    ] = False,
) -> None:
    """
    Create a new environment.

    If NAME is provided with --repo flags, creates non-interactively.
    If NAME is provided without --repo flags, opens TUI with name pre-filled.
    If no arguments, opens full TUI.
    """
    # If no repos specified, launch TUI
    if not repos:
        from qdpi.tui.app import run_tui

        run_tui(name)
        return

    # Non-interactive mode: must have name
    if not name:
        handle_error("Environment name is required when using --repo")

    # Parse repo:branch format
    repo_branches: dict[str, str] = {}
    for repo_spec in repos:
        if ":" not in repo_spec:
            handle_error(f"Invalid format: '{repo_spec}'. Use REPO:BRANCH format.")
        repo_name, branch = repo_spec.split(":", 1)
        repo_branches[repo_name] = branch

    manager = get_manager()

    def on_branch_not_found(
        repo_name: str,
        branch: str,
        available: list[str],
    ) -> str | None:
        """Handle missing branch - prompt for base branch."""
        console.print(f"[yellow]Branch '{branch}' does not exist in {repo_name}.[/yellow]")
        if not available:
            console.print("[red]No branches available.[/red]")
            return None

        # Show available branches
        console.print("Available branches:")
        for b in available[:10]:  # Show first 10
            console.print(f"  - {b}")
        if len(available) > 10:
            console.print(f"  ... and {len(available) - 10} more")

        if yes:
            # Default to main/master
            default_branch = "main" if "main" in available else available[0]
            console.print(f"Using '{default_branch}' as base branch")
            return default_branch

        base = Prompt.ask(
            "Enter base branch for new branch",
            choices=available,
            default="main" if "main" in available else available[0],
        )
        return base

    try:
        with console.status(f"Creating environment '{name}'..."):
            env = manager.create(
                name=name,
                repo_branches=repo_branches,
                fetch=not no_fetch,
                render_templates=not no_templates,
                on_branch_not_found=on_branch_not_found,
            )

        console.print(f"\n[green]Environment created:[/green] {env.path}")
        console.print("\nRepositories:")
        for repo in env.repos:
            console.print(f"  - {repo.name} ({repo.branch})")

        if env.generated_files:
            console.print("\nGenerated files:")
            for f in env.generated_files:
                console.print(f"  - {f}")

    except EnvironmentError as e:
        handle_error(str(e))


@app.command()
def review(
    pr_ref: Annotated[
        str | None,
        typer.Argument(help="PR URL or shorthand (e.g., backend#123)"),
    ] = None,
    repos: Annotated[
        list[str] | None,
        typer.Option(
            "--repo",
            "-r",
            help="Add companion repository with branch (format: REPO:BRANCH)",
        ),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", "-n", help="Custom environment name (default: pr-<number>)"),
    ] = None,
    no_fetch: Annotated[
        bool,
        typer.Option("--no-fetch", help="Skip fetching latest from remotes"),
    ] = False,
    no_templates: Annotated[
        bool,
        typer.Option("--no-templates", help="Skip template generation"),
    ] = False,
) -> None:
    """
    Create a review environment for a GitHub PR.

    Examples:
        qdpi review https://github.com/org/repo/pull/123
        qdpi review backend#123 -r frontend:main
        qdpi review backend#123 --name my-review
    """
    if not pr_ref:
        handle_error(
            "PR reference is required. "
            "Use a GitHub PR URL or shorthand like 'backend#123'.\n"
            "Example: qdpi review https://github.com/org/repo/pull/123"
        )

    try:
        config = load_config()
    except ConfigError as e:
        handle_error(str(e))

    repo_urls = {name: repo.url for name, repo in config.repositories.items()}
    parsed = parse_pr_reference(pr_ref, repo_urls)

    if not parsed:
        handle_error(
            f"Invalid PR reference: '{pr_ref}'. "
            "Use a GitHub PR URL or shorthand like 'backend#123'."
        )

    config_repo_name = _find_config_repo_name(parsed.full_name, config)
    if not config_repo_name:
        handle_error(
            f"Repository '{parsed.full_name}' not found in configuration. "
            f"Add it to your config.yaml first."
        )

    with console.status(f"Fetching PR #{parsed.number} from {parsed.full_name}..."):
        try:
            pr_metadata = GitHubOperations.get_pr_metadata(parsed)
        except GitHubError as e:
            handle_error(str(e))

    console.print(f"[bold]PR #{pr_metadata.number}:[/bold] {pr_metadata.title}")
    console.print(f"[dim]Branch:[/dim] {pr_metadata.head_ref}")
    console.print(f"[dim]Author:[/dim] @{pr_metadata.author}")
    console.print()

    env_name = name or f"pr-{parsed.number}"
    repo_branches: dict[str, str] = {config_repo_name: pr_metadata.head_ref}

    if repos:
        for repo_spec in repos:
            if ":" not in repo_spec:
                handle_error(f"Invalid format: '{repo_spec}'. Use REPO:BRANCH format.")
            repo_name, branch = repo_spec.split(":", 1)
            repo_branches[repo_name] = branch

    manager = EnvironmentManager(config)

    pr_info = PRInfo(
        number=pr_metadata.number,
        url=pr_metadata.url,
        title=pr_metadata.title,
        author=pr_metadata.author,
        head_ref=pr_metadata.head_ref,
        repo_name=config_repo_name,
    )

    def on_branch_not_found(
        repo_name: str,
        branch: str,
        available: list[str],
    ) -> str | None:
        console.print(f"[yellow]Branch '{branch}' does not exist in {repo_name}.[/yellow]")
        if not available:
            console.print("[red]No branches available.[/red]")
            return None

        console.print("Available branches:")
        for b in available[:10]:
            console.print(f"  - {b}")
        if len(available) > 10:
            console.print(f"  ... and {len(available) - 10} more")

        default_branch = "main" if "main" in available else available[0]
        base = Prompt.ask(
            "Enter base branch for new branch",
            choices=available,
            default=default_branch,
        )
        return base

    try:
        with console.status(f"Creating review environment '{env_name}'..."):
            env = manager.create(
                name=env_name,
                repo_branches=repo_branches,
                fetch=not no_fetch,
                render_templates=not no_templates,
                on_branch_not_found=on_branch_not_found,
                pr_info=pr_info,
            )

        console.print(f"\n[green]Review environment created:[/green] {env.path}")
        console.print("\nRepositories:")
        for repo in env.repos:
            if repo.name == config_repo_name:
                console.print(f"  - {repo.name} ({repo.branch}) [bold magenta]← PR[/bold magenta]")
            else:
                console.print(f"  - {repo.name} ({repo.branch})")

        if env.generated_files:
            console.print("\nGenerated files:")
            for f in env.generated_files:
                console.print(f"  - {f}")

    except EnvironmentError as e:
        handle_error(str(e))


def _find_config_repo_name(github_full_name: str, config: Config) -> str | None:
    """Find the config repo name that matches a GitHub owner/repo."""
    for repo_name, repo_config in config.repositories.items():
        parsed = parse_github_repo(repo_config.url)
        if parsed and parsed.lower() == github_full_name.lower():
            return repo_name
    return None


@app.command("list")
def list_envs(
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
    path_only: Annotated[
        bool,
        typer.Option("--path-only", help="Only print paths (one per line)"),
    ] = False,
    name_only: Annotated[
        bool,
        typer.Option("--name-only", help="Only print names (one per line)"),
    ] = False,
) -> None:
    """List all environments."""
    manager = get_manager()
    environments = manager.list_all()

    if not environments:
        if as_json:
            console.print("[]")
        else:
            console.print("No environments found.")
        return

    if path_only:
        for env in environments:
            console.print(env.path)
        return

    if name_only:
        for env in environments:
            console.print(env.name)
        return

    if as_json:
        data = []
        for env in environments:
            try:
                status = manager.get_status(env.name)
                repos_status = [
                    {
                        "name": r.name,
                        "branch": r.branch,
                        "has_uncommitted": r.status.has_uncommitted,
                        "uncommitted_count": r.status.uncommitted_count,
                        "commits_ahead": r.status.commits_ahead,
                        "commits_behind": r.status.commits_behind,
                        "error": r.status.error,
                    }
                    for r in status.repos
                ]
                env_data: dict[str, object] = {
                    "name": env.name,
                    "path": env.path,
                    "exists": status.exists_on_disk,
                    "repos": repos_status,
                }
                if env.pr_info:
                    env_data["pr_info"] = {
                        "number": env.pr_info.number,
                        "url": env.pr_info.url,
                        "title": env.pr_info.title,
                        "author": env.pr_info.author,
                        "head_ref": env.pr_info.head_ref,
                        "repo_name": env.pr_info.repo_name,
                    }
                data.append(env_data)
            except EnvironmentError:
                data.append(
                    {
                        "name": env.name,
                        "path": env.path,
                        "exists": False,
                        "repos": [],
                    }
                )
        console.print(json.dumps(data, indent=2))
        return

    # Table output
    table = Table(title="Environments")
    table.add_column("ENVIRONMENT", style="cyan")
    table.add_column("REPOSITORIES")
    table.add_column("STATUS")

    for env in environments:
        try:
            status = manager.get_status(env.name)
        except EnvironmentError:
            table.add_row(env.name, "?", "[red]✗ error[/red]")
            continue

        if not status.exists_on_disk:
            table.add_row(env.name, "?", "[red]✗ missing[/red]")
            continue

        # Build repo list and status
        repo_lines = []
        status_lines = []
        for r in status.repos:
            repo_lines.append(f"{r.name} ({r.branch})")
            if r.status.error:
                status_lines.append("[red]✗ error[/red]")
            elif r.status.has_uncommitted:
                status_lines.append(
                    f"[yellow]⚠ uncommitted ({r.status.uncommitted_count})[/yellow]"
                )
            elif r.status.commits_ahead > 0:
                status_lines.append(f"[blue]↑ {r.status.commits_ahead} unpushed[/blue]")
            else:
                status_lines.append("[green]✓ clean[/green]")

        env_display = env.name
        if env.pr_info:
            env_display = (
                f'{env.name}\n[dim]└─ "{env.pr_info.title}" by @{env.pr_info.author}[/dim]'
            )

        table.add_row(
            env_display,
            "\n".join(repo_lines),
            "\n".join(status_lines),
        )

    console.print(table)


@app.command()
def info(
    name: Annotated[str, typer.Argument(help="Environment name")],
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Show detailed information about an environment."""
    manager = get_manager()

    try:
        env = manager.get_info(name)
        status = manager.get_status(name)
    except EnvironmentError as e:
        handle_error(str(e))

    if as_json:
        data: dict[str, object] = {
            "name": env.name,
            "path": env.path,
            "created_at": env.created_at,
            "exists": status.exists_on_disk,
            "repos": [
                {
                    "name": r.name,
                    "branch": r.branch,
                    "worktree_path": r.worktree_path,
                    "status": {
                        "has_uncommitted": s.status.has_uncommitted,
                        "uncommitted_count": s.status.uncommitted_count,
                        "commits_ahead": s.status.commits_ahead,
                        "commits_behind": s.status.commits_behind,
                        "error": s.status.error,
                    },
                }
                for r, s in zip(env.repos, status.repos, strict=True)
            ],
            "generated_files": env.generated_files,
            "symlinks": [{"source": s.source, "target": s.target} for s in env.symlinks],
        }
        if env.pr_info:
            data["pr_info"] = {
                "number": env.pr_info.number,
                "url": env.pr_info.url,
                "title": env.pr_info.title,
                "author": env.pr_info.author,
                "head_ref": env.pr_info.head_ref,
                "repo_name": env.pr_info.repo_name,
            }
        console.print(json.dumps(data, indent=2))
        return

    # Pretty output
    console.print(f"\n[bold]Environment:[/bold] {env.name}")
    console.print(f"[bold]Path:[/bold] {env.path}")
    console.print(f"[bold]Created:[/bold] {env.created_at}")

    if env.pr_info:
        console.print("\n[bold magenta]Pull Request:[/bold magenta]")
        console.print(f"  #{env.pr_info.number}: {env.pr_info.title}")
        console.print(f"  Author: @{env.pr_info.author}")
        console.print(f"  URL: {env.pr_info.url}")

    if not status.exists_on_disk:
        console.print("\n[red]⚠ Environment directory is missing![/red]")
        return

    console.print("\n[bold]Repositories:[/bold]")
    for repo, repo_status in zip(env.repos, status.repos, strict=True):
        console.print(f"\n  [cyan]{repo.name}[/cyan]")
        console.print(f"    Branch: {repo.branch}")
        console.print(f"    Path: ./{repo.name}/")

        if repo_status.status.error:
            console.print(f"    Status: [red]✗ error ({repo_status.status.error})[/red]")
        elif repo_status.status.has_uncommitted:
            console.print(
                f"    Status: [yellow]⚠ uncommitted "
                f"({repo_status.status.uncommitted_count} files modified)[/yellow]"
            )
        elif repo_status.status.commits_ahead > 0:
            console.print(f"    Status: [blue]↑ {repo_status.status.commits_ahead} unpushed[/blue]")
        else:
            console.print("    Status: [green]✓ clean[/green]")

    if env.generated_files:
        console.print("\n[bold]Generated Files:[/bold]")
        for f in env.generated_files:
            console.print(f"  - {f}")

    if env.symlinks:
        console.print("\n[bold]Symlinks:[/bold]")
        for s in env.symlinks:
            console.print(f"  - {s.target} → {s.source}")
    else:
        console.print("\n[bold]Symlinks:[/bold]")
        console.print("  (none)")


@app.command()
def delete(
    names: Annotated[
        list[str],
        typer.Argument(help="Environment name(s) to delete"),
    ],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Delete even if there are unpushed changes"),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation prompt"),
    ] = False,
) -> None:
    """Delete one or more environments."""
    manager = get_manager()

    for name in names:
        try:
            status = manager.get_status(name)
        except EnvironmentError as e:
            error_console.print(f"[red]Error:[/red] {e}")
            continue

        # Check for unpushed changes
        has_issues = False
        if status.exists_on_disk and not force:
            for r in status.repos:
                if r.status.has_uncommitted:
                    console.print(
                        f"[yellow]⚠ Warning:[/yellow] {name}/{r.name} has "
                        f"{r.status.uncommitted_count} uncommitted changes"
                    )
                    has_issues = True
                if r.status.commits_ahead > 0:
                    console.print(
                        f"[yellow]⚠ Warning:[/yellow] {name}/{r.name} has "
                        f"{r.status.commits_ahead} unpushed commits"
                    )
                    has_issues = True

        if has_issues and not force:
            console.print(
                "\n[yellow]Use --force to delete environments with unpushed work.[/yellow]"
            )
            continue

        # Confirm deletion
        if not yes:
            if has_issues:
                prompt = f"Delete '{name}' with unpushed changes? This cannot be undone"
            elif status.exists_on_disk:
                prompt = f"Delete environment '{name}'?"
            else:
                prompt = f"Remove missing environment '{name}' from registry?"

            if not Confirm.ask(prompt, default=False):
                console.print("Aborted.")
                continue

        try:
            manager.delete(name, force=force)
            console.print(f"[green]Deleted environment '{name}'[/green]")
        except EnvironmentError as e:
            error_console.print(f"[red]Error deleting '{name}':[/red] {e}")


@app.command()
def path(
    name: Annotated[str, typer.Argument(help="Environment name")],
) -> None:
    """Print the absolute path to an environment."""
    manager = get_manager()
    try:
        env_path = manager.get_path(name)
        # Print raw path for shell integration
        print(str(env_path))
    except EnvironmentError as e:
        handle_error(str(e))


@app.command()
def config(
    path_only: Annotated[
        bool,
        typer.Option("--path", help="Only print config file path"),
    ] = False,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Show current configuration."""
    if path_only:
        print(str(GLOBAL_CONFIG_PATH))
        return

    try:
        cfg = load_config()
    except ConfigError as e:
        handle_error(str(e))

    if as_json:
        data = {
            "base_repos_dir": str(cfg.base_repos_dir),
            "environments_dir": str(cfg.environments_dir),
            "repositories": {name: {"url": repo.url} for name, repo in cfg.repositories.items()},
            "templates": [
                {
                    "source": str(t.source),
                    "destination": t.destination,
                    "when": t.when,
                }
                for t in cfg.templates
            ],
            "copy_files": [
                {
                    "source": str(c.source),
                    "destination": c.destination,
                    "when": c.when,
                }
                for c in cfg.copy_files
            ],
            "symlinks": [
                {
                    "source": s.source,
                    "target": s.target,
                    "when": s.when,
                }
                for s in cfg.symlinks
            ],
        }
        console.print(json.dumps(data, indent=2))
        return

    console.print(f"[bold]Configuration File:[/bold] {GLOBAL_CONFIG_PATH}")
    console.print(f"\n[bold]Base Repos Directory:[/bold] {cfg.base_repos_dir}")
    console.print(f"[bold]Environments Directory:[/bold] {cfg.environments_dir}")

    console.print(f"\n[bold]Repositories ({len(cfg.repositories)}):[/bold]")
    for name, repo in cfg.repositories.items():
        console.print(f"  [cyan]{name}[/cyan]: {repo.url}")

    if cfg.templates:
        console.print(f"\n[bold]Templates ({len(cfg.templates)}):[/bold]")
        for t in cfg.templates:
            when = f" (when: {', '.join(t.when)})" if t.when else ""
            console.print(f"  {t.source} → {t.destination}{when}")

    if cfg.copy_files:
        console.print(f"\n[bold]Copy Files ({len(cfg.copy_files)}):[/bold]")
        for c in cfg.copy_files:
            when = f" (when: {', '.join(c.when)})" if c.when else ""
            console.print(f"  {c.source} → {c.destination}{when}")

    if cfg.symlinks:
        console.print(f"\n[bold]Symlinks ({len(cfg.symlinks)}):[/bold]")
        for s in cfg.symlinks:
            console.print(f"  {s.source} → {s.target} (when: {', '.join(s.when)})")


if __name__ == "__main__":
    app()
