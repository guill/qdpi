# QDPI Design Specification

**Quick Development PIpeline** - A CLI tool for managing multi-repository development environments.

**Version**: 1.0.0  
**Status**: Design Complete  
**Last Updated**: 2026-01-01

---

## Table of Contents

1. [Overview](#1-overview)
2. [Goals and Non-Goals](#2-goals-and-non-goals)
3. [User Stories](#3-user-stories)
4. [Architecture](#4-architecture)
5. [Configuration](#5-configuration)
6. [CLI Commands](#6-cli-commands)
7. [TUI Design](#7-tui-design)
8. [Data Model](#8-data-model)
9. [Implementation Details](#9-implementation-details)
10. [Project Structure](#10-project-structure)
11. [Dependencies](#11-dependencies)
12. [Future Considerations](#12-future-considerations)

---

## 1. Overview

### 1.1 Problem Statement

Developers working across multiple related git repositories face challenges when:
- Working on features that span multiple repos simultaneously
- Managing multiple in-progress features, each requiring different repo combinations
- Keeping track of which environments have uncommitted or unpushed changes
- Setting up consistent development environments with proper documentation

### 1.2 Solution

QDPI (Quick Development PIpeline) is a CLI tool that creates isolated **environments** - directories containing:
- Git worktrees of selected repositories (each on a user-specified branch)
- Generated files from Jinja2 templates (e.g., AGENTS.md, Makefile)
- Copied static files
- Symlinks between repositories when needed

### 1.3 Key Concepts

| Term | Definition |
|------|------------|
| **Environment** | A named directory containing one or more repository worktrees and generated files |
| **Base Repository** | The primary clone of a repository, from which worktrees are created |
| **Worktree** | A git worktree - a lightweight checkout sharing the git object store with its base |
| **Template** | A Jinja2 file that gets rendered into each environment |

### 1.4 Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.10+ | Native Jinja2, team familiarity, rapid development |
| CLI Framework | Typer | Modern, type-hint based, excellent UX |
| TUI Framework | Textual | Async-native, beautiful, actively maintained |
| Rich Output | Rich | Pretty tables, progress bars, colors |
| Config | PyYAML + Pydantic | Typed config with validation |
| Templating | Jinja2 | Industry standard, powerful |
| Git Operations | subprocess | Simple, reliable, no abstraction leaks |
| Async | asyncio | For parallel branch fetching |

---

## 2. Goals and Non-Goals

### 2.1 Goals

1. **Create environments** with user-selected repositories, each on a user-specified branch
2. **Support both CLI and TUI** for environment creation
3. **Track environment status** - show uncommitted/unpushed changes across all repos
4. **Safe deletion** with warnings for unpushed work
5. **Configurable** via YAML - not hardcoded to any specific repositories
6. **Template system** for generating files (AGENTS.md, Makefile, etc.)
7. **Symlink support** for inter-repository dependencies
8. **Space efficient** using git worktrees instead of full clones

### 2.2 Non-Goals (v1)

1. ~~Environment templates/presets~~ (deferred to v2)
2. ~~Init scripts per repository~~ (deferred to v2)
3. ~~Build orchestration / dependency graph~~ (out of scope)
4. ~~Auto-cleanup of old environments~~ (manual only)
5. ~~GUI application~~ (CLI/TUI only)
6. ~~Integration with CI/CD~~ (out of scope)

---

## 3. User Stories

### 3.1 Create Environment (CLI)

**As a developer**, I want to create an environment with specific repos on specific branches so I can work on a feature that spans multiple repositories.

```bash
# Create environment with two repos on different branches
$ qdpi create payment-feature \
    --repo backend:feature/payments \
    --repo frontend:main

Creating environment 'payment-feature'...
  [1/4] Ensuring base repos exist...
        backend: using existing base repo
        frontend: using existing base repo
  [2/4] Fetching latest branches...
        backend: fetched 12 new commits
        frontend: up to date
  [3/4] Creating worktrees...
        backend (feature/payments): created
        frontend (main): created
  [4/4] Generating files...
        AGENTS.md: generated
        Makefile: skipped (condition not met)

Environment created at: ~/qdpi-envs/payment-feature/
```

### 3.2 Create Environment (TUI)

**As a developer**, I want an interactive interface to select repos and branches so I don't have to remember exact branch names.

```bash
$ qdpi create
# Opens TUI (see Section 7)
```

### 3.3 List Environments

**As a developer**, I want to see all my environments and their status so I know which have uncommitted work.

```bash
$ qdpi list

ENVIRONMENT            REPOSITORIES                              STATUS
─────────────────────────────────────────────────────────────────────────────
payment-feature        backend (feature/payments)                ⚠ uncommitted
                       frontend (main)                           ✓ clean

add-caching            backend (feature/caching)                 ✓ clean
                       docs (main)                               ↑ 2 unpushed

api-refactor           infra (feature/api-v2)                    ✓ clean
                       api (feature/api-v2)                      ✓ clean
```

### 3.4 Delete Environment

**As a developer**, I want to delete an environment with safety checks so I don't accidentally lose unpushed work.

```bash
$ qdpi delete api-refactor
Environment 'api-refactor' is clean. Delete? [y/N]: y
Deleted environment 'api-refactor'.

$ qdpi delete add-caching
⚠ Warning: Environment 'add-caching' has unpushed changes:
  - docs: 2 commits ahead of origin/main

Are you sure you want to delete? This cannot be undone. [y/N]: n
Aborted.

$ qdpi delete add-caching --force
Deleted environment 'add-caching'.
```

### 3.5 Environment Info

**As a developer**, I want to see detailed info about an environment.

```bash
$ qdpi info payment-feature

Environment: payment-feature
Path: ~/qdpi-envs/payment-feature
Created: 2026-01-01 14:30:00

Repositories:
  backend
    Branch: feature/payments
    Status: ⚠ uncommitted (2 files modified)
    Path: ./backend/

  frontend
    Branch: main
    Status: ✓ clean
    Path: ./frontend/

Generated Files:
  - AGENTS.md

Symlinks:
  (none)
```

### 3.6 Navigate to Environment

**As a developer**, I want to quickly navigate to an environment directory.

```bash
# Print path (for use with cd)
$ qdpi path payment-feature
/home/user/qdpi-envs/payment-feature

# Common pattern
$ cd $(qdpi path payment-feature)
```

---

## 4. Architecture

### 4.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Interface                          │
├─────────────────────────────────────────────────────────────────┤
│                    CLI (Typer)    │    TUI (Textual)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Core Services                            │
├─────────────────────────────────────────────────────────────────┤
│  EnvironmentManager  │  RepoManager  │  TemplateEngine          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Data Layer                                │
├─────────────────────────────────────────────────────────────────┤
│  ConfigLoader  │  EnvironmentRegistry  │  GitOperations         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      File System / Git                          │
├─────────────────────────────────────────────────────────────────┤
│  ~/.config/qdpi/   │   ~/qdpi-envs/   │   ~/.local/share/qdpi/  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 Directory Structure

```
~/.config/qdpi/                    # User configuration
├── config.yaml                    # Main configuration file
└── templates/                     # Jinja2 templates
    ├── AGENTS.md.j2
    └── Makefile.j2

~/.local/share/qdpi/               # Application data
├── repos/                         # Base repositories (worktree sources)
│   ├── backend/
│   ├── frontend/
│   └── ...
└── registry.json                  # Environment registry

~/qdpi-envs/                       # Environments (configurable)
├── payment-feature/
│   ├── AGENTS.md                  # Generated
│   ├── backend/                   # Worktree
│   └── frontend/                  # Worktree
└── add-caching/
    ├── AGENTS.md
    ├── backend/
    └── docs/
```

### 4.3 Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **CLI** | Parse commands, invoke services, format output |
| **TUI** | Interactive environment creation flow |
| **EnvironmentManager** | Create, delete, list environments |
| **RepoManager** | Clone base repos, create worktrees, fetch branches |
| **TemplateEngine** | Render Jinja2 templates with environment context |
| **ConfigLoader** | Load and validate config.yaml |
| **EnvironmentRegistry** | Track created environments (JSON file) |
| **GitOperations** | Execute git commands, parse output |

---

## 5. Configuration

### 5.1 Config File Location

Primary: `~/.config/qdpi/config.yaml`

The tool should also check for a local `.qdpi.yaml` in the current directory for project-specific overrides.

### 5.2 Config Schema

```yaml
# ~/.config/qdpi/config.yaml

# Where base repositories are cloned (worktree sources)
# Default: ~/.local/share/qdpi/repos
base_repos_dir: ~/.local/share/qdpi/repos

# Where environments are created
# Default: ~/qdpi-envs
environments_dir: ~/qdpi-envs

# Repository definitions
repositories:
  # Key is the repository name (used in commands and templates)
  backend:
    # Required: Git URL (SSH or HTTPS)
    url: git@github.com:your-org/backend.git
  
  frontend:
    url: git@github.com:your-org/frontend.git
  
  infra:
    url: git@github.com:your-org/infra.git
  
  api:
    url: git@github.com:your-org/api.git
  
  docs:
    url: git@github.com:your-org/docs.git

# Jinja2 templates to render into environments
templates:
  - source: ~/.config/qdpi/templates/AGENTS.md.j2
    destination: AGENTS.md
    # Optional: only generate when these repos are present
    # when: [backend, frontend]
  
  - source: ~/.config/qdpi/templates/Makefile.j2
    destination: Makefile
    when: [backend, frontend]

# Static files to copy (no templating)
copy_files:
  - source: ~/.config/qdpi/files/.editorconfig
    destination: .editorconfig
    # Optional: only copy when these repos are present
    # when: [backend]

# Symlinks to create between repositories
symlinks:
  - source: backend/shared      # Relative to environment root
    target: frontend/src/shared
    when: [backend, frontend]  # Required: repos that must be present
```

### 5.3 Config Validation

The config is validated at load time using Pydantic:

```python
from pydantic import BaseModel, field_validator
from pathlib import Path

class RepoConfig(BaseModel):
    url: str

class TemplateConfig(BaseModel):
    source: Path
    destination: str
    when: list[str] | None = None

class CopyFileConfig(BaseModel):
    source: Path
    destination: str
    when: list[str] | None = None

class SymlinkConfig(BaseModel):
    source: str
    target: str
    when: list[str]

class Config(BaseModel):
    base_repos_dir: Path = Path("~/.local/share/qdpi/repos")
    environments_dir: Path = Path("~/qdpi-envs")
    repositories: dict[str, RepoConfig]
    templates: list[TemplateConfig] = []
    copy_files: list[CopyFileConfig] = []
    symlinks: list[SymlinkConfig] = []
    
    @field_validator('base_repos_dir', 'environments_dir', mode='before')
    @classmethod
    def expand_path(cls, v):
        return Path(v).expanduser()
```

---

## 6. CLI Commands

### 6.1 Command Overview

| Command | Description |
|---------|-------------|
| `qdpi create [NAME]` | Create a new environment (TUI if no args) |
| `qdpi list` | List all environments with status |
| `qdpi info <NAME>` | Show detailed environment info |
| `qdpi delete <NAME>` | Delete an environment |
| `qdpi path <NAME>` | Print environment path |
| `qdpi config` | Show current configuration |
| `qdpi init` | Create default config file |

### 6.2 Command Details

#### `qdpi create`

```
Usage: qdpi create [OPTIONS] [NAME]

Create a new environment.

If NAME is provided with --repo flags, creates non-interactively.
If NAME is provided without --repo flags, opens TUI with name pre-filled.
If no arguments, opens full TUI.

Arguments:
  NAME    Environment name (optional)

Options:
  -r, --repo REPO:BRANCH    Add repository with branch (can be repeated)
  --no-fetch                Skip fetching latest from remotes
  --no-templates            Skip template generation
  -y, --yes                 Skip confirmation prompts

Examples:
  qdpi create                                    # Full TUI
  qdpi create my-feature                         # TUI with name pre-filled
  qdpi create my-feature -r backend:main         # Non-interactive
  qdpi create my-feature -r backend:feature/x -r infra:main
```

#### `qdpi list`

```
Usage: qdpi list [OPTIONS]

List all environments.

Options:
  --json          Output as JSON
  --path-only     Only print paths (one per line)
  --name-only     Only print names (one per line)

Output Columns:
  ENVIRONMENT     Environment name
  REPOSITORIES    Repo names with branches
  STATUS          Git status indicators:
                    ✓ clean      - No uncommitted changes, up to date
                    ⚠ uncommitted - Has uncommitted changes
                    ↑ N unpushed  - N commits ahead of remote
                    ✗ error      - Could not determine status
```

#### `qdpi delete`

```
Usage: qdpi delete [OPTIONS] NAME [NAME...]

Delete one or more environments.

Arguments:
  NAME    Environment name(s) to delete

Options:
  -f, --force     Delete even if there are unpushed changes
  -y, --yes       Skip confirmation prompt

Safety:
  - Warns if any repository has uncommitted changes
  - Warns if any repository has unpushed commits
  - Requires --force to delete environments with unpushed work
```

#### `qdpi info`

```
Usage: qdpi info [OPTIONS] NAME

Show detailed information about an environment.

Arguments:
  NAME    Environment name

Options:
  --json    Output as JSON
```

#### `qdpi path`

```
Usage: qdpi path NAME

Print the absolute path to an environment.

Arguments:
  NAME    Environment name

Example:
  cd $(qdpi path my-feature)
```

#### `qdpi config`

```
Usage: qdpi config [OPTIONS]

Show current configuration.

Options:
  --path    Only print config file path
  --json    Output as JSON
```

#### `qdpi init`

```
Usage: qdpi init [OPTIONS]

Initialize qdpi with a default configuration file.

Options:
  --force    Overwrite existing config file

Creates:
  ~/.config/qdpi/config.yaml     (main config)
  ~/.config/qdpi/templates/      (template directory)
```

---

## 7. TUI Design

### 7.1 Overview

The TUI is a multi-step wizard for creating environments:

1. **Name Input** - Enter environment name
2. **Repository Selection** - Select repos with checkbox list
3. **Branch Selection** - For each selected repo, choose branch
4. **Confirmation** - Review and confirm

### 7.2 Screen Mockups

#### Step 1: Name Input

```
┌─────────────────────────────────────────────────────────────────┐
│  QDPI - Create Environment                              [1/4]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Environment Name:                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ payment-feature█                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Name must be a valid directory name (letters, numbers,         │
│  hyphens, underscores).                                         │
│                                                                 │
│                                                                 │
│                                                                 │
│                                                                 │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  [Enter] Continue    [Esc] Cancel                               │
└─────────────────────────────────────────────────────────────────┘
```

#### Step 2: Repository Selection

```
┌─────────────────────────────────────────────────────────────────┐
│  QDPI - Create Environment                              [2/4]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Select repositories to include:                                │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ [x] backend                                              │   │
│  │ [x] frontend                                             │   │
│  │ [ ] infra                                                │   │
│  │ [ ] api                                                  │   │
│  │ [ ] docs                                                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Selected: 2 repositories                                       │
│                                                                 │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  [↑↓] Navigate  [Space] Toggle  [Enter] Continue  [Esc] Back    │
└─────────────────────────────────────────────────────────────────┘
```

#### Step 3: Branch Selection

```
┌─────────────────────────────────────────────────────────────────┐
│  QDPI - Create Environment                              [3/4]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Select branch for each repository:                             │
│                                                                 │
│  backend                                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ feature/payments█                                        │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │   main                                                   │   │
│  │   develop                                                │   │
│  │ → feature/payments                                       │   │
│  │   feature/caching                                        │   │
│  │   bugfix/memory-leak                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  frontend: main                                                 │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  [↑↓] Select  [Tab] Next repo  [Enter] Continue  [Esc] Back     │
└─────────────────────────────────────────────────────────────────┘
```

Note: Branch list is populated asynchronously. While fetching:
```
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ main█                                                    │   │
│  ├─────────────────────────────────────────────────────────┤   │
│  │   ⏳ Fetching branches...                                │   │
│  └─────────────────────────────────────────────────────────┘   │
```

#### Step 4: Confirmation

```
┌─────────────────────────────────────────────────────────────────┐
│  QDPI - Create Environment                              [4/4]   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Review your environment:                                       │
│                                                                 │
│  Name: payment-feature                                          │
│  Path: ~/qdpi-envs/payment-feature/                             │
│                                                                 │
│  Repositories:                                                  │
│    • backend              → feature/payments                    │
│    • frontend             → main                                │
│                                                                 │
│  Files to generate:                                             │
│    • AGENTS.md                                                  │
│                                                                 │
│  Symlinks:                                                      │
│    • frontend/src/shared → backend/shared                       │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│  [Enter] Create    [Esc] Back    [Ctrl+C] Cancel                │
└─────────────────────────────────────────────────────────────────┘
```

### 7.3 TUI Implementation Notes

1. **Framework**: Textual (Python async TUI framework)
2. **Async Branch Fetching**: Use `asyncio` to fetch branches in background while user selects repos
3. **Autocomplete**: Branch input field filters as user types
4. **Validation**: Real-time validation of environment name
5. **Navigation**: Standard vim-like keybindings (j/k) in addition to arrows

---

## 8. Data Model

### 8.1 Environment Registry

Stored at: `~/.local/share/qdpi/registry.json`

```json
{
  "version": 1,
  "environments": {
    "payment-feature": {
      "name": "payment-feature",
      "path": "/home/user/qdpi-envs/payment-feature",
      "created_at": "2026-01-01T14:30:00Z",
      "repos": [
        {
          "name": "backend",
          "branch": "feature/payments",
          "worktree_path": "/home/user/qdpi-envs/payment-feature/backend"
        },
        {
          "name": "frontend", 
          "branch": "main",
          "worktree_path": "/home/user/qdpi-envs/payment-feature/frontend"
        }
      ],
      "generated_files": ["AGENTS.md"],
      "symlinks": [
        {
          "source": "backend/shared",
          "target": "frontend/src/shared"
        }
      ]
    }
  }
}
```

### 8.2 Internal Models

```python
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

@dataclass
class RepoInstance:
    """A repository within an environment."""
    name: str
    branch: str
    worktree_path: Path

@dataclass
class Symlink:
    """A symlink within an environment."""
    source: str  # Relative to environment root
    target: str  # Relative to environment root

@dataclass
class Environment:
    """A development environment."""
    name: str
    path: Path
    created_at: datetime
    repos: list[RepoInstance]
    generated_files: list[str]
    symlinks: list[Symlink]

@dataclass
class RepoStatus:
    """Git status for a repository."""
    name: str
    branch: str
    has_uncommitted: bool
    uncommitted_count: int
    commits_ahead: int
    commits_behind: int
    error: str | None = None
```

---

## 9. Implementation Details

### 9.1 Git Operations

All git operations use subprocess for simplicity and reliability:

```python
import subprocess
import asyncio
from pathlib import Path

class GitOperations:
    @staticmethod
    def clone(url: str, dest: Path) -> None:
        """Clone a repository."""
        subprocess.run(
            ["git", "clone", url, str(dest)],
            check=True,
            capture_output=True,
            text=True
        )
    
    @staticmethod
    def create_worktree(base_repo: Path, branch: str, dest: Path) -> None:
        """Create a worktree for a branch."""
        # First, ensure branch exists (create if needed)
        subprocess.run(
            ["git", "worktree", "add", str(dest), branch],
            cwd=base_repo,
            check=True,
            capture_output=True,
            text=True
        )
    
    @staticmethod
    def remove_worktree(base_repo: Path, worktree_path: Path) -> None:
        """Remove a worktree."""
        subprocess.run(
            ["git", "worktree", "remove", str(worktree_path)],
            cwd=base_repo,
            check=True,
            capture_output=True,
            text=True
        )
    
    @staticmethod
    async def fetch_branches(repo_path: Path) -> list[str]:
        """Fetch and list all remote branches (async)."""
        # Fetch latest
        proc = await asyncio.create_subprocess_exec(
            "git", "fetch", "--all", "--prune",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        # List branches
        proc = await asyncio.create_subprocess_exec(
            "git", "branch", "-r", "--format=%(refname:short)",
            cwd=repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        
        branches = []
        for line in stdout.decode().strip().split('\n'):
            if line and not line.endswith('/HEAD'):
                # Remove 'origin/' prefix
                branch = line.replace('origin/', '')
                branches.append(branch)
        
        return sorted(set(branches))
    
    @staticmethod
    def get_status(repo_path: Path) -> dict:
        """Get repository status."""
        result = {
            "has_uncommitted": False,
            "uncommitted_count": 0,
            "commits_ahead": 0,
            "commits_behind": 0,
        }
        
        # Check for uncommitted changes
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        lines = [l for l in proc.stdout.strip().split('\n') if l]
        result["uncommitted_count"] = len(lines)
        result["has_uncommitted"] = len(lines) > 0
        
        # Check ahead/behind
        proc = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", "@{u}...HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        if proc.returncode == 0:
            parts = proc.stdout.strip().split('\t')
            if len(parts) == 2:
                result["commits_behind"] = int(parts[0])
                result["commits_ahead"] = int(parts[1])
        
        return result
```

### 9.2 Template Rendering

```python
from jinja2 import Environment as JinjaEnv, FileSystemLoader
from pathlib import Path

class TemplateEngine:
    def __init__(self):
        self.jinja_env = JinjaEnv(
            loader=FileSystemLoader('/'),  # Allow absolute paths
            autoescape=False
        )
    
    def render(
        self,
        template_path: Path,
        env_name: str,
        repos: list[RepoInstance],
        symlinks: list[Symlink],
        env_path: Path
    ) -> str:
        """Render a template with environment context."""
        template = self.jinja_env.get_template(str(template_path))
        
        # Build context
        context = {
            "env_name": env_name,
            "repos": [
                {"name": r.name, "branch": r.branch}
                for r in repos
            ],
            "repo_names": {r.name for r in repos},
            "symlinks": [
                {"source": s.source, "target": s.target}
                for s in symlinks
            ],
            "env_path": str(env_path),
            "created_at": datetime.now().isoformat(),
        }
        
        return template.render(**context)
    
    def should_render(
        self,
        template_config: TemplateConfig,
        repo_names: set[str]
    ) -> bool:
        """Check if template should be rendered based on 'when' condition."""
        if template_config.when is None:
            return True
        return all(repo in repo_names for repo in template_config.when)
```

### 9.3 Environment Creation Flow

```python
class EnvironmentManager:
    def create(
        self,
        name: str,
        repo_branches: dict[str, str],  # repo_name -> branch
        fetch: bool = True,
        render_templates: bool = True
    ) -> Environment:
        """Create a new environment."""
        
        # Validate name
        if not self._is_valid_name(name):
            raise ValueError(f"Invalid environment name: {name}")
        
        if self.registry.exists(name):
            raise ValueError(f"Environment '{name}' already exists")
        
        env_path = self.config.environments_dir / name
        repo_names = set(repo_branches.keys())
        
        try:
            # Step 1: Ensure base repos exist
            for repo_name in repo_branches:
                self._ensure_base_repo(repo_name)
            
            # Step 2: Fetch latest (optional)
            if fetch:
                for repo_name in repo_branches:
                    self._fetch_repo(repo_name)
            
            # Step 3: Create environment directory
            env_path.mkdir(parents=True)
            
            # Step 4: Create worktrees
            repo_instances = []
            for repo_name, branch in repo_branches.items():
                worktree_path = env_path / repo_name
                base_repo = self.config.base_repos_dir / repo_name
                
                self.git.create_worktree(base_repo, branch, worktree_path)
                
                repo_instances.append(RepoInstance(
                    name=repo_name,
                    branch=branch,
                    worktree_path=worktree_path
                ))
            
            # Step 5: Create symlinks
            active_symlinks = []
            for symlink_config in self.config.symlinks:
                if all(r in repo_names for r in symlink_config.when):
                    source = env_path / symlink_config.source
                    target = env_path / symlink_config.target
                    
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(source)
                    
                    active_symlinks.append(Symlink(
                        source=symlink_config.source,
                        target=symlink_config.target
                    ))
            
            # Step 6: Render templates
            generated_files = []
            if render_templates:
                for template_config in self.config.templates:
                    if self.template_engine.should_render(template_config, repo_names):
                        content = self.template_engine.render(
                            template_config.source,
                            name,
                            repo_instances,
                            active_symlinks,
                            env_path
                        )
                        
                        dest = env_path / template_config.destination
                        dest.write_text(content)
                        generated_files.append(template_config.destination)
            
            # Step 7: Copy static files
            for copy_config in self.config.copy_files:
                if copy_config.when is None or all(r in repo_names for r in copy_config.when):
                    source = Path(copy_config.source).expanduser()
                    dest = env_path / copy_config.destination
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
            
            # Step 8: Register environment
            environment = Environment(
                name=name,
                path=env_path,
                created_at=datetime.now(),
                repos=repo_instances,
                generated_files=generated_files,
                symlinks=active_symlinks
            )
            
            self.registry.add(environment)
            
            return environment
            
        except Exception as e:
            # Cleanup on failure
            if env_path.exists():
                shutil.rmtree(env_path)
            raise
```

### 9.4 Status Checking

```python
def get_environment_status(self, name: str) -> list[RepoStatus]:
    """Get status of all repos in an environment."""
    env = self.registry.get(name)
    statuses = []
    
    for repo in env.repos:
        try:
            git_status = self.git.get_status(repo.worktree_path)
            statuses.append(RepoStatus(
                name=repo.name,
                branch=repo.branch,
                has_uncommitted=git_status["has_uncommitted"],
                uncommitted_count=git_status["uncommitted_count"],
                commits_ahead=git_status["commits_ahead"],
                commits_behind=git_status["commits_behind"]
            ))
        except Exception as e:
            statuses.append(RepoStatus(
                name=repo.name,
                branch=repo.branch,
                has_uncommitted=False,
                uncommitted_count=0,
                commits_ahead=0,
                commits_behind=0,
                error=str(e)
            ))
    
    return statuses
```

---

## 10. Project Structure

```
qdpi/
├── pyproject.toml              # Project metadata and dependencies
├── README.md                   # User documentation
├── LICENSE                     # License file
├── src/
│   └── qdpi/
│       ├── __init__.py
│       ├── __main__.py         # Entry point (python -m qdpi)
│       ├── cli.py              # Typer CLI definition
│       ├── tui/
│       │   ├── __init__.py
│       │   ├── app.py          # Main Textual app
│       │   ├── screens/
│       │   │   ├── __init__.py
│       │   │   ├── name_input.py
│       │   │   ├── repo_select.py
│       │   │   ├── branch_select.py
│       │   │   └── confirmation.py
│       │   └── widgets/
│       │       ├── __init__.py
│       │       └── branch_picker.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── environment.py  # EnvironmentManager
│       │   ├── repo.py         # RepoManager
│       │   ├── template.py     # TemplateEngine
│       │   └── git.py          # GitOperations
│       ├── config/
│       │   ├── __init__.py
│       │   ├── loader.py       # ConfigLoader
│       │   └── models.py       # Pydantic models
│       ├── registry/
│       │   ├── __init__.py
│       │   └── registry.py     # EnvironmentRegistry
│       └── utils/
│           ├── __init__.py
│           └── paths.py        # Path utilities
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Pytest fixtures
│   ├── test_cli.py
│   ├── test_environment.py
│   ├── test_git.py
│   ├── test_template.py
│   └── test_config.py
└── examples/
    ├── config.yaml             # Example configuration
    └── templates/
        ├── AGENTS.md.j2
        └── Makefile.j2
```

---

## 11. Dependencies

### 11.1 Runtime Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "typer>=0.9.0",          # CLI framework
    "textual>=0.50.0",       # TUI framework
    "rich>=13.0.0",          # Rich text formatting
    "pyyaml>=6.0",           # YAML parsing
    "pydantic>=2.0.0",       # Config validation
    "jinja2>=3.0.0",         # Templating
]
```

### 11.2 Development Dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "mypy>=1.0.0",
    "ruff>=0.1.0",
]
```

### 11.3 System Requirements

- Python 3.10+
- Git 2.20+ (for worktree support)

---

## 12. Future Considerations

### 12.1 Version 2 Features

| Feature | Description |
|---------|-------------|
| **Environment Templates** | Pre-defined repo combinations (e.g., "full-stack", "frontend-only") |
| **Init Scripts** | Per-repo scripts that run after initial clone (e.g., add remotes) |
| **Post-Create Hooks** | User-defined scripts that run after environment creation |
| **Environment Forking** | Clone an existing environment to a new name |
| **Batch Operations** | Run commands across all repos in an environment |

### 12.2 Potential Enhancements

1. **Shell Completion** - Bash/Zsh/Fish completion for environment names
2. **Editor Integration** - `qdpi code <name>` to open in VS Code
3. **Sync Command** - Pull latest changes across all repos
4. **Archive Command** - Compress old environments instead of deleting
5. **Import/Export** - Share environment definitions with team

### 12.3 Known Limitations

1. **Same Branch in Multiple Environments** - Git worktrees don't allow the same branch in multiple worktrees. Users must use different branches or force with caution.
2. **Large Repositories** - Initial clone of large repos can be slow (mitigated by one-time base repo setup).
3. **Submodules** - Not explicitly handled; may require manual `git submodule update` in worktrees.

---

## Appendix A: Example AGENTS.md.j2 Template

```jinja2
# {{ env_name }} Environment

This environment contains the following repositories.

## Repositories

{% for repo in repos %}
### {{ repo.name }}
- **Branch**: `{{ repo.branch }}`
- **Path**: `./{{ repo.name }}/`

{% endfor %}

---

## Repository Details

{% if 'backend' in repo_names %}
### backend

Core backend service. Handles business logic, data persistence, and API endpoints.

**Entry Points:**
- `main.py` - Start the server
- `src/` - Core library
- `tests/` - Test suite

**Useful Commands:**
```bash
python main.py --host 0.0.0.0 --port 8000
```

{% endif %}
{% if 'frontend' in repo_names %}
### frontend

Web frontend application built with modern JavaScript frameworks.

**Entry Points:**
- `src/` - Application source
- `package.json` - npm scripts

**Useful Commands:**
```bash
npm install
npm run dev
```

{% endif %}
{% if 'infra' in repo_names %}
### infra

Infrastructure and deployment configuration. Manages cloud resources and CI/CD.

**Entry Points:**
- `terraform/` - Infrastructure as code
- `k8s/` - Kubernetes manifests
- `scripts/` - Deployment scripts

{% endif %}
{% if 'api' in repo_names %}
### api

API gateway and service layer. Handles authentication, rate limiting, and request routing.

**Entry Points:**
- `src/` - API source code
- `config/` - Configuration files

{% endif %}
{% if 'docs' in repo_names %}
### docs

Documentation and guides for the project.

**Entry Points:**
- `docs/` - Documentation source
- `mkdocs.yml` - MkDocs configuration

{% endif %}

## Quick Reference

| Repository | Branch | Path |
|------------|--------|------|
{% for repo in repos %}
| {{ repo.name }} | `{{ repo.branch }}` | `./{{ repo.name }}/` |
{% endfor %}

{% if symlinks %}
## Symlinks

The following symlinks connect repositories:
{% for link in symlinks %}
- `{{ link.target }}` → `{{ link.source }}`
{% endfor %}
{% endif %}

---

*Generated by qdpi on {{ created_at }}*
```

---

## Appendix B: Installation Instructions

### From PyPI (Recommended)

```bash
# Using pipx (isolated install)
pipx install qdpi

# Using pip
pip install qdpi
```

### From Source

```bash
git clone https://github.com/your-org/qdpi.git
cd qdpi
pip install -e .
```

### First-Time Setup

```bash
# Initialize config
qdpi init

# Edit config to add your repositories
$EDITOR ~/.config/qdpi/config.yaml

# Create your first environment
qdpi create
```

---

*End of Design Specification*
