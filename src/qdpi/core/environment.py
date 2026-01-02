"""Environment manager for QDPI."""

import contextlib
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from qdpi.config.models import Config
from qdpi.core.git import GitError, GitOperations, RepoStatus
from qdpi.core.template import TemplateEngine, TemplateEngineError
from qdpi.registry.registry import (
    Environment,
    EnvironmentRegistry,
    RegistryError,
    RepoInstance,
    SymlinkEntry,
)
from qdpi.utils.paths import is_valid_environment_name


class EnvironmentError(Exception):
    """Raised when environment operations fail."""


@dataclass
class EnvironmentStatus:
    """Status of an environment."""

    name: str
    path: Path
    exists_on_disk: bool
    repos: list["RepoStatusInfo"]


@dataclass
class RepoStatusInfo:
    """Extended repo status with name and branch."""

    name: str
    branch: str
    status: RepoStatus


class EnvironmentManager:
    """Manages development environments."""

    def __init__(
        self,
        config: Config,
        registry: EnvironmentRegistry | None = None,
        git: GitOperations | None = None,
        template_engine: TemplateEngine | None = None,
    ):
        """
        Initialize the environment manager.

        Args:
            config: QDPI configuration.
            registry: Environment registry (optional, creates default).
            git: Git operations (optional, creates default).
            template_engine: Template engine (optional, creates default).
        """
        self.config = config
        self.registry = registry or EnvironmentRegistry()
        self.git = git or GitOperations()
        self.template_engine = template_engine or TemplateEngine()

    def _ensure_base_repo(self, repo_name: str) -> Path:
        """
        Ensure a base repository exists, cloning if necessary.

        Args:
            repo_name: Name of the repository.

        Returns:
            Path to the base repository.

        Raises:
            EnvironmentError: If repository not in config or clone fails.
        """
        if repo_name not in self.config.repositories:
            raise EnvironmentError(f"Repository '{repo_name}' not found in configuration")

        repo_config = self.config.repositories[repo_name]
        base_path = self.config.base_repos_dir / repo_name

        if base_path.exists():
            return base_path

        # Clone the repository
        self.config.base_repos_dir.mkdir(parents=True, exist_ok=True)
        try:
            GitOperations.clone(repo_config.url, base_path)
        except GitError as e:
            raise EnvironmentError(f"Failed to clone {repo_name}: {e}") from e

        return base_path

    def _fetch_repo(self, repo_name: str) -> None:
        """Fetch latest from remote for a repository."""
        base_path = self.config.base_repos_dir / repo_name
        if base_path.exists():
            with contextlib.suppress(GitError):
                GitOperations.fetch(base_path)

    def create(
        self,
        name: str,
        repo_branches: dict[str, str],
        fetch: bool = True,
        render_templates: bool = True,
        on_branch_not_found: Callable[[str, str, list[str]], str | None] | None = None,
    ) -> Environment:
        """
        Create a new environment.

        Args:
            name: Environment name.
            repo_branches: Mapping of repo names to branch names.
            fetch: Whether to fetch latest from remotes.
            render_templates: Whether to render templates.
            on_branch_not_found: Callback when branch doesn't exist.
                Signature: (repo_name: str, branch: str, available_branches: list[str]) -> str | None
                Returns new branch name to create, or None to abort.

        Returns:
            Created Environment object.

        Raises:
            EnvironmentError: If creation fails.
        """
        # Validate name
        if not is_valid_environment_name(name):
            raise EnvironmentError(
                f"Invalid environment name: '{name}'. "
                "Use only letters, numbers, hyphens, and underscores."
            )

        if self.registry.exists(name):
            raise EnvironmentError(f"Environment '{name}' already exists")

        env_path = self.config.environments_dir / name
        if env_path.exists():
            raise EnvironmentError(f"Directory already exists: {env_path}")

        repo_names = set(repo_branches.keys())

        try:
            # Step 1: Ensure base repos exist
            for repo_name in repo_branches:
                self._ensure_base_repo(repo_name)

            # Step 2: Fetch latest (optional)
            if fetch:
                for repo_name in repo_branches:
                    self._fetch_repo(repo_name)

            # Step 3: Validate branches exist (and handle missing ones)
            resolved_branches: dict[str, tuple[str, str | None]] = {}
            for repo_name, branch in repo_branches.items():
                base_repo = self.config.base_repos_dir / repo_name
                if GitOperations.branch_exists(base_repo, branch):
                    resolved_branches[repo_name] = (branch, None)
                else:
                    # Branch doesn't exist - call callback
                    if on_branch_not_found:
                        available = GitOperations.list_branches(base_repo)
                        base_branch = on_branch_not_found(repo_name, branch, available)
                        if base_branch is None:
                            raise EnvironmentError(
                                f"Branch '{branch}' does not exist in {repo_name}"
                            )
                        # Create new branch from base
                        resolved_branches[repo_name] = (branch, base_branch)
                    else:
                        raise EnvironmentError(f"Branch '{branch}' does not exist in {repo_name}")

            # Step 4: Create environment directory
            env_path.mkdir(parents=True)

            # Step 5: Create worktrees
            repo_instances: list[RepoInstance] = []
            for repo_name, (branch, create_from) in resolved_branches.items():
                worktree_path = env_path / repo_name
                base_repo = self.config.base_repos_dir / repo_name

                actual_branch = GitOperations.create_worktree(
                    base_repo=base_repo,
                    branch=branch,
                    dest=worktree_path,
                    create_branch_from=create_from,
                )

                repo_instances.append(
                    RepoInstance(
                        name=repo_name,
                        branch=actual_branch,
                        worktree_path=str(worktree_path),
                    )
                )

            # Step 6: Create symlinks
            active_symlinks: list[SymlinkEntry] = []
            for symlink_config in self.config.symlinks:
                if all(r in repo_names for r in symlink_config.when):
                    source = env_path / symlink_config.source
                    target = env_path / symlink_config.target

                    if not source.exists():
                        continue  # Skip if source doesn't exist

                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(source.resolve())

                    active_symlinks.append(
                        SymlinkEntry(
                            source=symlink_config.source,
                            target=symlink_config.target,
                        )
                    )

            # Step 7: Render templates
            generated_files: list[str] = []
            if render_templates:
                for template_config in self.config.templates:
                    if self.template_engine.should_render(template_config, repo_names):
                        try:
                            content = self.template_engine.render(
                                template_config.source,
                                name,
                                repo_instances,
                                active_symlinks,
                                env_path,
                            )
                            dest = env_path / template_config.destination
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            dest.write_text(content)
                            generated_files.append(template_config.destination)
                        except TemplateEngineError:
                            # Template rendering failures are non-fatal
                            pass

            # Step 8: Copy static files
            for copy_config in self.config.copy_files:
                if copy_config.when is None or all(r in repo_names for r in copy_config.when):
                    source = copy_config.source
                    if source.exists():
                        dest = env_path / copy_config.destination
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, dest)

            # Step 9: Register environment
            environment = Environment.create(
                name=name,
                path=env_path,
                repos=repo_instances,
                generated_files=generated_files,
                symlinks=active_symlinks,
            )

            self.registry.add(environment)

            return environment

        except Exception as e:
            # Cleanup on failure
            if env_path.exists():
                shutil.rmtree(env_path, ignore_errors=True)
            if isinstance(e, EnvironmentError):
                raise
            raise EnvironmentError(f"Failed to create environment: {e}") from e

    def delete(self, name: str, force: bool = False) -> None:
        """
        Delete an environment.

        Args:
            name: Environment name.
            force: Force deletion even with unpushed changes.

        Raises:
            EnvironmentError: If deletion fails or has unpushed changes.
        """
        try:
            env = self.registry.get(name)
        except RegistryError as e:
            raise EnvironmentError(str(e)) from e

        env_path = Path(env.path)

        # Check for unpushed changes if not forcing
        if not force and env_path.exists():
            statuses = self.get_status(name)
            unpushed = [
                s for s in statuses.repos if s.status.commits_ahead > 0 or s.status.has_uncommitted
            ]
            if unpushed:
                repo_info = ", ".join(
                    f"{s.name} ({s.status.commits_ahead} unpushed, {s.status.uncommitted_count} uncommitted)"
                    for s in unpushed
                )
                raise EnvironmentError(
                    f"Environment has unpushed changes: {repo_info}. Use --force to delete anyway."
                )

        # Remove worktrees from base repos
        for repo in env.repos:
            worktree_path = Path(repo.worktree_path)
            base_repo = self.config.base_repos_dir / repo.name
            if base_repo.exists():
                with contextlib.suppress(GitError):
                    GitOperations.remove_worktree(base_repo, worktree_path, force=force)
                with contextlib.suppress(GitError):
                    GitOperations.prune_worktrees(base_repo)

        # Remove directory
        if env_path.exists():
            shutil.rmtree(env_path, ignore_errors=True)

        # Remove from registry
        with contextlib.suppress(RegistryError):
            self.registry.remove(name)

    def get_status(self, name: str) -> EnvironmentStatus:
        """
        Get status of an environment.

        Args:
            name: Environment name.

        Returns:
            EnvironmentStatus with repo statuses.

        Raises:
            EnvironmentError: If environment not found.
        """
        try:
            env = self.registry.get(name)
        except RegistryError as e:
            raise EnvironmentError(str(e)) from e

        env_path = Path(env.path)
        exists_on_disk = env_path.exists()

        repo_statuses: list[RepoStatusInfo] = []
        for repo in env.repos:
            worktree_path = Path(repo.worktree_path)
            if worktree_path.exists():
                status = GitOperations.get_status(worktree_path)
            else:
                status = RepoStatus(
                    has_uncommitted=False,
                    uncommitted_count=0,
                    commits_ahead=0,
                    commits_behind=0,
                    current_branch=repo.branch,
                    error="Worktree not found",
                )

            repo_statuses.append(
                RepoStatusInfo(
                    name=repo.name,
                    branch=repo.branch,
                    status=status,
                )
            )

        return EnvironmentStatus(
            name=name,
            path=env_path,
            exists_on_disk=exists_on_disk,
            repos=repo_statuses,
        )

    def list_all(self) -> list[Environment]:
        """List all environments."""
        return self.registry.list_all()

    def get_info(self, name: str) -> Environment:
        """
        Get detailed info about an environment.

        Args:
            name: Environment name.

        Returns:
            Environment object.

        Raises:
            EnvironmentError: If environment not found.
        """
        try:
            return self.registry.get(name)
        except RegistryError as e:
            raise EnvironmentError(str(e)) from e

    def get_path(self, name: str) -> Path:
        """
        Get the path to an environment.

        Args:
            name: Environment name.

        Returns:
            Path to the environment directory.

        Raises:
            EnvironmentError: If environment not found.
        """
        try:
            env = self.registry.get(name)
            return Path(env.path)
        except RegistryError as e:
            raise EnvironmentError(str(e)) from e
