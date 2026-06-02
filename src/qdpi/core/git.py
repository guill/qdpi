"""Git operations for QDPI."""

import asyncio
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    """Raised when a git operation fails."""


@dataclass
class RepoStatus:
    """Git status for a repository."""

    has_uncommitted: bool
    uncommitted_count: int
    commits_ahead: int
    commits_behind: int
    current_branch: str
    error: str | None = None


class GitOperations:
    """Git operations using subprocess."""

    @staticmethod
    def _run(
        args: list[str],
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command."""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                check=check,
                capture_output=True,
                text=True,
            )
            return result
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else ""
            raise GitError(f"Git command failed: git {' '.join(args)}\n{stderr}") from e

    @staticmethod
    def clone(url: str, dest: Path) -> None:
        """Clone a repository."""
        GitOperations._run(["clone", url, str(dest)])

    @staticmethod
    def fetch(repo_path: Path) -> None:
        """Fetch all remotes."""
        GitOperations._run(["fetch", "--all", "--prune"], cwd=repo_path)

    @staticmethod
    def get_current_branch(repo_path: Path) -> str:
        """Get the current branch name."""
        result = GitOperations._run(["branch", "--show-current"], cwd=repo_path)
        return result.stdout.strip()

    @staticmethod
    def get_default_branch(repo_path: Path) -> str:
        """Get the default branch (usually main or master)."""
        # Try to get from remote HEAD
        result = GitOperations._run(
            ["symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=repo_path,
            check=False,
        )
        if result.returncode == 0:
            # Returns something like "refs/remotes/origin/main"
            return result.stdout.strip().split("/")[-1]

        # Fall back to checking common defaults
        for branch in ["main", "master"]:
            result = GitOperations._run(
                ["rev-parse", "--verify", f"origin/{branch}"],
                cwd=repo_path,
                check=False,
            )
            if result.returncode == 0:
                return branch

        return "main"  # Ultimate fallback

    @staticmethod
    def list_remotes(repo_path: Path) -> list[str]:
        """Return remote names, preferring origin first."""
        result = GitOperations._run(["remote"], cwd=repo_path, check=False)
        if result.returncode != 0:
            return ["origin"]
        remotes = [r.strip() for r in result.stdout.splitlines() if r.strip()]
        ordered: list[str] = []
        if "origin" in remotes:
            ordered.append("origin")
        for r in remotes:
            if r != "origin":
                ordered.append(r)
        return ordered or ["origin"]

    @staticmethod
    def resolve_branch_ref(repo_path: Path, branch: str) -> str | None:
        """Resolve a branch shortname to a ref that exists in the repo.

        Searches each remote first (origin preferred), then local branches.
        Remotes are preferred so that a freshly fetched environment is based
        on the up-to-date remote ref (e.g. ``origin/main``) rather than a
        possibly-stale local branch of the same name. Falls back to a local
        branch only when the branch exists nowhere on a remote.

        Returns the ref string suitable for `git worktree add ... <ref>`,
        or None if the branch can't be found anywhere.
        """
        for remote in GitOperations.list_remotes(repo_path):
            candidate = f"{remote}/{branch}"
            result = GitOperations._run(
                ["rev-parse", "--verify", candidate],
                cwd=repo_path,
                check=False,
            )
            if result.returncode == 0:
                return candidate

        local = GitOperations._run(
            ["rev-parse", "--verify", f"refs/heads/{branch}"],
            cwd=repo_path,
            check=False,
        )
        if local.returncode == 0:
            return branch

        return None

    @staticmethod
    def branch_exists(repo_path: Path, branch: str) -> bool:
        """Check if a branch exists locally or on any configured remote."""
        return GitOperations.resolve_branch_ref(repo_path, branch) is not None

    @staticmethod
    def list_branches(repo_path: Path, remote_only: bool = True) -> list[str]:
        """List all branches.

        Strips every known remote prefix so the result is a flat list of
        branch shortnames suitable for selection by the user.
        """
        if remote_only:
            result = GitOperations._run(
                ["branch", "-r", "--format=%(refname:short)"],
                cwd=repo_path,
            )
        else:
            result = GitOperations._run(
                ["branch", "-a", "--format=%(refname:short)"],
                cwd=repo_path,
            )

        remotes = GitOperations.list_remotes(repo_path)
        branches: list[str] = []
        for line in result.stdout.strip().split("\n"):
            if not line or line.endswith("/HEAD"):
                continue
            stripped = line
            for remote in remotes:
                prefix = f"{remote}/"
                if stripped.startswith(prefix):
                    stripped = stripped[len(prefix) :]
                    break
            branches.append(stripped)

        return sorted(set(branches))

    @staticmethod
    def is_branch_in_worktree(repo_path: Path, branch: str) -> bool:
        """Check if a branch is already checked out in another worktree."""
        result = GitOperations._run(["worktree", "list", "--porcelain"], cwd=repo_path)

        # Parse worktree list output
        current_worktree_branch = None
        for line in result.stdout.strip().split("\n"):
            if line.startswith("branch "):
                # Format: "branch refs/heads/main"
                current_worktree_branch = line.split("/")[-1]
                if current_worktree_branch == branch:
                    return True

        return False

    @staticmethod
    def generate_tracking_branch_name(base_branch: str) -> str:
        """Generate a unique tracking branch name."""
        short_id = secrets.token_hex(4)  # 8 character hex string
        return f"tracking/{short_id}/{base_branch}"

    @staticmethod
    def create_worktree(
        base_repo: Path,
        branch: str,
        dest: Path,
        create_branch_from: str | None = None,
    ) -> str:
        """
        Create a worktree for a branch.

        Args:
            base_repo: Path to the base repository.
            branch: Branch name to check out.
            dest: Destination path for the worktree.
            create_branch_from: If set, create a new branch from this base.

        Returns:
            The actual branch name used (may differ if tracking branch created).
        """
        if create_branch_from:
            base_ref = GitOperations.resolve_branch_ref(base_repo, create_branch_from)
            if base_ref is None:
                raise GitError(
                    f"Base branch '{create_branch_from}' not found on any remote"
                )
            GitOperations._run(
                ["worktree", "add", "-b", branch, str(dest), base_ref],
                cwd=base_repo,
            )
            return branch

        ref = GitOperations.resolve_branch_ref(base_repo, branch)
        if ref is None:
            raise GitError(f"Branch '{branch}' not found locally or on any remote")

        if GitOperations.is_branch_in_worktree(base_repo, branch):
            tracking_branch = GitOperations.generate_tracking_branch_name(branch)
            GitOperations._run(
                ["worktree", "add", "-b", tracking_branch, str(dest), ref],
                cwd=base_repo,
            )
            return tracking_branch

        if ref == branch:
            GitOperations._run(
                ["worktree", "add", str(dest), branch],
                cwd=base_repo,
            )
            return branch

        GitOperations._run(
            ["worktree", "add", "-b", branch, str(dest), ref],
            cwd=base_repo,
        )
        return branch

    @staticmethod
    def remove_worktree(base_repo: Path, worktree_path: Path, force: bool = False) -> None:
        """Remove a worktree."""
        args = ["worktree", "remove", str(worktree_path)]
        if force:
            args.append("--force")
        GitOperations._run(args, cwd=base_repo)

    @staticmethod
    def prune_worktrees(base_repo: Path) -> None:
        """Prune stale worktree metadata."""
        GitOperations._run(["worktree", "prune"], cwd=base_repo)

    @staticmethod
    async def fetch_branches_async(repo_path: Path) -> list[str]:
        """Fetch and list all remote branches (async)."""
        # Fetch latest
        proc = await asyncio.create_subprocess_exec(
            "git",
            "fetch",
            "--all",
            "--prune",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

        # List branches
        proc = await asyncio.create_subprocess_exec(
            "git",
            "branch",
            "-r",
            "--format=%(refname:short)",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        branches = []
        for line in stdout.decode().strip().split("\n"):
            if line and not line.endswith("/HEAD"):
                branch = line.replace("origin/", "")
                branches.append(branch)

        return sorted(set(branches))

    @staticmethod
    async def get_default_branch_async(repo_path: Path) -> str:
        """
        Get the default branch (usually main or master) asynchronously.

        Mirrors get_default_branch() but uses asyncio.create_subprocess_exec
        so it can run concurrently with other fetches in TUI workers.
        """
        # Try to get from remote HEAD
        proc = await asyncio.create_subprocess_exec(
            "git",
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode().strip().split("/")[-1]

        # Fall back to checking common defaults
        for branch in ["main", "master"]:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "rev-parse",
                "--verify",
                f"origin/{branch}",
                cwd=repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            if proc.returncode == 0:
                return branch

        return "main"  # Ultimate fallback

    @staticmethod
    def get_status(repo_path: Path) -> RepoStatus:
        """Get repository status."""
        error = None
        has_uncommitted = False
        uncommitted_count = 0
        commits_ahead = 0
        commits_behind = 0
        current_branch = ""

        try:
            # Get current branch
            result = GitOperations._run(
                ["branch", "--show-current"],
                cwd=repo_path,
                check=False,
            )
            current_branch = result.stdout.strip()

            # Check for uncommitted changes
            result = GitOperations._run(
                ["status", "--porcelain"],
                cwd=repo_path,
                check=False,
            )
            lines = [line for line in result.stdout.strip().split("\n") if line]
            uncommitted_count = len(lines)
            has_uncommitted = uncommitted_count > 0

            # Check ahead/behind
            result = GitOperations._run(
                ["rev-list", "--left-right", "--count", "@{u}...HEAD"],
                cwd=repo_path,
                check=False,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split("\t")
                if len(parts) == 2:
                    commits_behind = int(parts[0])
                    commits_ahead = int(parts[1])

        except Exception as e:
            error = str(e)

        return RepoStatus(
            has_uncommitted=has_uncommitted,
            uncommitted_count=uncommitted_count,
            commits_ahead=commits_ahead,
            commits_behind=commits_behind,
            current_branch=current_branch,
            error=error,
        )
