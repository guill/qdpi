"""Tests for GitOperations branch resolution and worktree creation.

These tests use real temporary git repositories so that the interaction with
git's actual ref resolution (local vs. remote-tracking refs) is exercised
faithfully. The central guarantee under test: when creating a worktree, qdpi
prefers the freshly fetched remote ref over a possibly-stale local branch of
the same name.
"""

import subprocess
from pathlib import Path

import pytest

from qdpi.core.git import GitError, GitOperations


def _git(*args: str, cwd: Path) -> str:
    """Run a git command in cwd and return stripped stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(path: Path, default_branch: str = "main") -> None:
    """Initialize a git repo with deterministic identity/config."""
    path.mkdir(parents=True, exist_ok=True)
    _git("init", f"--initial-branch={default_branch}", cwd=path)
    _git("config", "user.email", "test@example.com", cwd=path)
    _git("config", "user.name", "Test User", cwd=path)


def _commit(path: Path, filename: str, content: str, message: str) -> str:
    """Create a commit in path and return its SHA."""
    (path / filename).write_text(content)
    _git("add", filename, cwd=path)
    _git("commit", "-m", message, cwd=path)
    return _git("rev-parse", "HEAD", cwd=path)


@pytest.fixture
def remote_repo(tmp_path: Path) -> Path:
    """A bare-style 'origin' repo with an initial commit on main."""
    origin = tmp_path / "origin"
    _init_repo(origin)
    _commit(origin, "README.md", "v1", "initial commit")
    return origin


@pytest.fixture
def cloned_repo(tmp_path: Path, remote_repo: Path) -> Path:
    """A clone of remote_repo (has local main + origin/main tracking ref)."""
    clone = tmp_path / "clone"
    GitOperations.clone(str(remote_repo), clone)
    return clone


def _rev(repo: Path, ref: str) -> str:
    return _git("rev-parse", ref, cwd=repo)


def _worktree_head(worktree: Path) -> str:
    return _git("rev-parse", "HEAD", cwd=worktree)


class TestResolveBranchRef:
    """resolve_branch_ref must prefer remote refs over local branches."""

    def test_prefers_remote_over_local_for_default_branch(
        self, cloned_repo: Path
    ) -> None:
        # A fresh clone has both refs/heads/main and origin/main.
        # The fix requires the remote ref to win.
        assert GitOperations.resolve_branch_ref(cloned_repo, "main") == "origin/main"

    def test_falls_back_to_local_when_no_remote_counterpart(
        self, cloned_repo: Path
    ) -> None:
        # Create a purely local branch with no remote counterpart.
        _git("branch", "local-only", cwd=cloned_repo)
        assert GitOperations.resolve_branch_ref(cloned_repo, "local-only") == "local-only"

    def test_returns_none_for_unknown_branch(self, cloned_repo: Path) -> None:
        assert GitOperations.resolve_branch_ref(cloned_repo, "does-not-exist") is None

    def test_resolves_remote_only_feature_branch(
        self, remote_repo: Path, cloned_repo: Path
    ) -> None:
        # Add a feature branch on the remote only, then fetch.
        _git("branch", "feature/x", cwd=remote_repo)
        GitOperations.fetch(cloned_repo)
        assert GitOperations.resolve_branch_ref(cloned_repo, "feature/x") == "origin/feature/x"


class TestBranchExists:
    def test_true_for_remote_branch(self, cloned_repo: Path) -> None:
        assert GitOperations.branch_exists(cloned_repo, "main") is True

    def test_true_for_local_only_branch(self, cloned_repo: Path) -> None:
        _git("branch", "local-only", cwd=cloned_repo)
        assert GitOperations.branch_exists(cloned_repo, "local-only") is True

    def test_false_for_missing_branch(self, cloned_repo: Path) -> None:
        assert GitOperations.branch_exists(cloned_repo, "nope") is False


class TestCreateWorktreeUsesFreshRemote:
    """The core regression guard: worktrees track the freshly fetched remote."""

    def test_worktree_uses_fresh_remote_not_stale_local(
        self, tmp_path: Path, remote_repo: Path, cloned_repo: Path
    ) -> None:
        # Advance the remote past the clone's stale local main.
        new_sha = _commit(remote_repo, "feature.txt", "v2", "remote moves ahead")
        stale_local_sha = _rev(cloned_repo, "refs/heads/main")
        assert new_sha != stale_local_sha

        # Simulate qdpi's create flow: fetch, then create the worktree.
        GitOperations.fetch(cloned_repo)
        assert _rev(cloned_repo, "origin/main") == new_sha
        # Local main must still be stale (fetch does not move it).
        assert _rev(cloned_repo, "refs/heads/main") == stale_local_sha

        dest = tmp_path / "env" / "repo"
        actual_branch = GitOperations.create_worktree(
            base_repo=cloned_repo,
            branch="main",
            dest=dest,
        )

        # main is checked out in the base clone, so a tracking branch is made,
        # but it must be based on the FRESH remote commit.
        assert actual_branch.startswith("tracking/")
        assert actual_branch.endswith("/main")
        assert _worktree_head(dest) == new_sha

    def test_worktree_for_remote_only_branch_creates_local_branch(
        self, tmp_path: Path, remote_repo: Path, cloned_repo: Path
    ) -> None:
        # Feature branch exists only on the remote.
        _git("checkout", "-b", "feature/y", cwd=remote_repo)
        feature_sha = _commit(remote_repo, "y.txt", "y", "feature commit")
        _git("checkout", "main", cwd=remote_repo)
        GitOperations.fetch(cloned_repo)

        dest = tmp_path / "env" / "repo"
        actual_branch = GitOperations.create_worktree(
            base_repo=cloned_repo,
            branch="feature/y",
            dest=dest,
        )

        # Not checked out anywhere, so a real local branch named feature/y is created.
        assert actual_branch == "feature/y"
        assert _worktree_head(dest) == feature_sha
        # Confirm it's an actual local branch in the worktree, not detached HEAD.
        assert _git("branch", "--show-current", cwd=dest) == "feature/y"

    def test_worktree_for_local_only_branch_still_works(
        self, tmp_path: Path, cloned_repo: Path
    ) -> None:
        # A local-only branch (no remote counterpart) should still resolve.
        _git("branch", "local-only", cwd=cloned_repo)
        local_sha = _rev(cloned_repo, "refs/heads/local-only")

        dest = tmp_path / "env" / "repo"
        actual_branch = GitOperations.create_worktree(
            base_repo=cloned_repo,
            branch="local-only",
            dest=dest,
        )

        assert actual_branch == "local-only"
        assert _worktree_head(dest) == local_sha

    def test_create_branch_from_uses_fresh_remote_base(
        self, tmp_path: Path, remote_repo: Path, cloned_repo: Path
    ) -> None:
        # Advance remote so origin/main is ahead of stale local main.
        new_sha = _commit(remote_repo, "z.txt", "v2", "remote ahead")
        GitOperations.fetch(cloned_repo)

        dest = tmp_path / "env" / "repo"
        actual_branch = GitOperations.create_worktree(
            base_repo=cloned_repo,
            branch="brand-new",
            dest=dest,
            create_branch_from="main",
        )

        # New branch created off the fresh remote commit, not stale local main.
        assert actual_branch == "brand-new"
        assert _worktree_head(dest) == new_sha
        assert _git("branch", "--show-current", cwd=dest) == "brand-new"

    def test_create_branch_from_missing_base_raises(
        self, tmp_path: Path, cloned_repo: Path
    ) -> None:
        dest = tmp_path / "env" / "repo"
        with pytest.raises(GitError, match="not found"):
            GitOperations.create_worktree(
                base_repo=cloned_repo,
                branch="brand-new",
                dest=dest,
                create_branch_from="no-such-base",
            )

    def test_unknown_branch_raises(self, tmp_path: Path, cloned_repo: Path) -> None:
        dest = tmp_path / "env" / "repo"
        with pytest.raises(GitError, match="not found"):
            GitOperations.create_worktree(
                base_repo=cloned_repo,
                branch="ghost-branch",
                dest=dest,
            )
