# QDPI - Quick Development PIpeline

A CLI tool for managing multi-repository development environments using git worktrees.

## Installation

```bash
git clone https://github.com/guill/qdpi.git
cd qdpi
pip install -e .
```

## Quick Start

```bash
# Initialize configuration
qdpi init

# Edit config to add your repositories
$EDITOR ~/.config/qdpi/config.yaml

# Create an environment (interactive TUI)
qdpi create

# Create an environment (CLI)
qdpi create my-feature -r backend:feature/branch -r frontend:main

# List environments
qdpi list

# Get environment info
qdpi info my-feature

# Delete an environment
qdpi delete my-feature
```

## Reviewing Pull Requests

QDPI can create review environments directly from GitHub PR URLs, making it easy to check out PRs locally.

### Prerequisites

- [GitHub CLI](https://cli.github.com/) (`gh`) must be installed and authenticated

### Usage

```bash
# Review a PR by URL
qdpi review https://github.com/org/backend/pull/123

# Review a PR using shorthand (repo name from your config)
qdpi review backend#123

# Add companion repositories at specific branches
qdpi review backend#123 -r frontend:main -r api:main

# Use a custom environment name (default: pr-<number>)
qdpi review backend#123 --name review-auth-fix
```

### How It Works

1. QDPI fetches PR metadata (title, author, branch) via `gh pr view`
2. Creates a worktree for the PR's branch
3. Optionally adds companion repos at specified branches
4. Registers the environment with PR metadata for easy tracking

### Example Workflow

```bash
# You get pinged on a PR - pull it down
$ qdpi review https://github.com/org/backend/pull/456 -r frontend:main

PR #456: Fix authentication token refresh
Branch: fix/token-refresh
Author: @alice

Creating review environment 'pr-456'...
  ✓ backend → fix/token-refresh (PR)
  ✓ frontend → main

Environment created: ~/qdpi-envs/pr-456

# Navigate to the environment
$ cd $(qdpi path pr-456)

# Run your tests, review code, etc.
$ make test

# When done, clean up
$ qdpi delete pr-456
```

### Listing PR Environments

PR environments show additional metadata in listings:

```bash
$ qdpi list

ENVIRONMENT     REPOSITORIES              STATUS
─────────────────────────────────────────────────────
my-feature      backend (feat/x)          ✓ clean
                frontend (main)           ✓ clean

pr-456          backend (fix/token)       ✓ clean
└─ "Fix auth token refresh" by @alice
                frontend (main)           ✓ clean
```

## License

MIT
