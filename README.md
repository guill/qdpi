# QDPI - Quick Development PIpeline

A CLI tool for managing multi-repository development environments using git worktrees.

## Installation

```bash
pip install qdpi
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

## License

MIT
