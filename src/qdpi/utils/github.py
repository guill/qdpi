"""GitHub utilities for QDPI."""

import json
import re
import subprocess
from dataclasses import dataclass


@dataclass
class ParsedPR:
    """Parsed PR reference."""

    owner: str
    repo: str
    number: int

    @property
    def full_name(self) -> str:
        """Get the full repo name (owner/repo)."""
        return f"{self.owner}/{self.repo}"

    @property
    def ref(self) -> str:
        """Get the PR reference for gh CLI (owner/repo#number)."""
        return f"{self.owner}/{self.repo}#{self.number}"


def parse_github_repo(url: str) -> str | None:
    """
    Extract 'owner/repo' from a GitHub URL.

    Supports:
        - SSH: git@github.com:owner/repo.git
        - HTTPS: https://github.com/owner/repo.git
        - HTTPS (no .git): https://github.com/owner/repo

    Args:
        url: A GitHub repository URL.

    Returns:
        The owner/repo string, or None if not a GitHub URL.
    """
    # SSH: git@github.com:owner/repo.git
    if url.startswith("git@github.com:"):
        path = url.removeprefix("git@github.com:")
        path = path.removesuffix(".git")
        # Validate it looks like owner/repo
        if "/" in path and len(path.split("/")) == 2:
            return path
        return None

    # HTTPS: https://github.com/owner/repo.git or https://github.com/owner/repo
    match = re.match(r"https?://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$", url)
    if match:
        return match.group(1)

    return None


def parse_pr_url(url: str) -> ParsedPR | None:
    """
    Parse a GitHub PR URL into its components.

    Supports:
        - https://github.com/owner/repo/pull/123
        - https://github.com/owner/repo/pull/123/files
        - https://github.com/owner/repo/pull/123/commits

    Args:
        url: A GitHub PR URL.

    Returns:
        ParsedPR with owner, repo, and number, or None if invalid.
    """
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)(?:/.*)?$",
        url,
    )
    if match:
        return ParsedPR(
            owner=match.group(1),
            repo=match.group(2),
            number=int(match.group(3)),
        )
    return None


def parse_pr_shorthand(shorthand: str, repo_urls: dict[str, str]) -> ParsedPR | None:
    """
    Parse a PR shorthand like 'backend#123' using configured repo URLs.

    Args:
        shorthand: A string like 'reponame#123'.
        repo_urls: Mapping of repo names to their URLs.

    Returns:
        ParsedPR with owner, repo, and number, or None if invalid.
    """
    match = re.match(r"^([a-zA-Z0-9_-]+)#(\d+)$", shorthand)
    if not match:
        return None

    repo_name = match.group(1)
    pr_number = int(match.group(2))

    if repo_name not in repo_urls:
        return None

    github_path = parse_github_repo(repo_urls[repo_name])
    if not github_path:
        return None

    parts = github_path.split("/")
    if len(parts) != 2:
        return None

    return ParsedPR(
        owner=parts[0],
        repo=parts[1],
        number=pr_number,
    )


def parse_pr_reference(
    reference: str,
    repo_urls: dict[str, str] | None = None,
) -> ParsedPR | None:
    """
    Parse a PR reference, either a full URL or shorthand.

    Args:
        reference: Either a full PR URL or shorthand like 'backend#123'.
        repo_urls: Mapping of repo names to URLs (required for shorthand).

    Returns:
        ParsedPR with owner, repo, and number, or None if invalid.
    """
    # Try as URL first
    parsed = parse_pr_url(reference)
    if parsed:
        return parsed

    # Try as shorthand
    if repo_urls and "#" in reference:
        return parse_pr_shorthand(reference, repo_urls)

    return None


class GitHubError(Exception):
    """Raised when GitHub operations fail."""


@dataclass
class PRMetadata:
    """PR metadata fetched from GitHub."""

    number: int
    title: str
    author: str
    head_ref: str  # Branch name
    url: str


class GitHubOperations:
    """GitHub operations using the gh CLI."""

    @staticmethod
    def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
        """Run a gh CLI command."""
        try:
            result = subprocess.run(
                ["gh", *args],
                check=True,
                capture_output=True,
                text=True,
            )
            return result
        except FileNotFoundError as e:
            raise GitHubError("gh CLI not found. Install it from https://cli.github.com/") from e
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else ""
            raise GitHubError(f"gh command failed: {stderr}") from e

    @staticmethod
    def check_auth() -> bool:
        """Check if gh CLI is authenticated."""
        try:
            GitHubOperations._run_gh(["auth", "status"])
            return True
        except GitHubError:
            return False

    @staticmethod
    def get_pr_metadata(parsed_pr: ParsedPR) -> PRMetadata:
        """Fetch PR metadata from GitHub."""
        result = GitHubOperations._run_gh(
            [
                "pr",
                "view",
                str(parsed_pr.number),
                "--repo",
                parsed_pr.full_name,
                "--json",
                "number,title,author,headRefName,url",
            ]
        )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise GitHubError(f"Failed to parse PR metadata: {e}") from e

        return PRMetadata(
            number=data["number"],
            title=data["title"],
            author=data["author"]["login"],
            head_ref=data["headRefName"],
            url=data["url"],
        )
