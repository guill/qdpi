# QDPI PROJECT KNOWLEDGE BASE

**Generated:** 2026-01-02
**Commit:** c13da0c
**Branch:** main

## OVERVIEW

CLI/TUI tool for managing multi-repository development environments using git worktrees. Stack: Python 3.10+, Typer (CLI), Textual (TUI), Pydantic (config), Jinja2 (templates).

## STRUCTURE

```
qdpi/
├── src/qdpi/
│   ├── cli.py          # Typer commands (init, create, list, info, delete, path, config)
│   ├── __main__.py     # Entry: `python -m qdpi`
│   ├── config/         # YAML config loading + Pydantic models
│   ├── core/           # Business logic: environment.py (main), git.py, template.py
│   ├── registry/       # JSON persistence for environments
│   ├── tui/            # Textual app with 4-screen wizard flow
│   │   ├── app.py      # QdpiApp orchestrates screen transitions
│   │   └── screens/    # NameInput → RepoSelect → BranchSelect → Confirmation
│   └── utils/          # Path validation
├── examples/           # Sample config.yaml + Jinja2 templates
├── tests/              # pytest-asyncio (stub)
└── pyproject.toml      # uv/hatch build, ruff+mypy config
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Add CLI command | `cli.py` | Typer decorator, use `get_manager()` |
| Modify env creation | `core/environment.py` → `create()` | ~150 lines, handles worktrees/templates/symlinks |
| Add config option | `config/models.py` | Pydantic BaseModel, affects `config.yaml` schema |
| TUI screen flow | `tui/app.py` | Message handlers: `on_*_screen_submitted` |
| Add TUI screen | `tui/screens/` | Inherit `Screen[None]`, post `Message` subclass |
| Template rendering | `core/template.py` | Jinja2 with `env.*` context |

## CODE MAP

| Symbol | Type | Location | Role |
|--------|------|----------|------|
| `EnvironmentManager` | Class | core/environment.py:45 | Central orchestrator: create/delete/status |
| `QdpiApp` | Class | tui/app.py:15 | Textual App[int], 4-step wizard |
| `Config` | Class | config/models.py | Pydantic root config model |
| `GitOperations` | Class | core/git.py | Static methods for git/worktree ops |
| `Registry` | Class | registry/registry.py | JSON-backed environment persistence |
| `app` | Typer | cli.py:20 | CLI entry point |

## CONVENTIONS

### Type Safety (STRICT)
- `mypy --strict` enabled
- **Never** use `as any`, `@ts-ignore`, `# type: ignore`
- All functions must have type annotations
- Generic types require parameters: `Screen[None]`, `App[int]`

### Code Style
- ruff: 100 char lines, select `E,F,I,UP,B,SIM`
- `zip()` calls require `strict=True`
- Use `contextlib.suppress()` over empty `except: pass`
- Imports: stdlib → third-party → local (ruff auto-sorts)

### TUI Patterns
- Screens communicate via `Message` subclasses (not direct returns)
- App catches messages in `on_<screen>_<message>` handlers
- Screen transitions: `pop_screen()` then `push_screen()`
- All screens inherit `Screen[None]` (no return value)

### Git Worktree Flow
1. Ensure base repo exists in `base_repos_dir`
2. Fetch (optional) to get latest branches
3. Create worktree in `environments_dir/{env_name}/{repo_name}`
4. Run `git worktree add` with branch (create if not exists)

## ANTI-PATTERNS (THIS PROJECT)

- **Don't** suppress type errors - fix them properly
- **Don't** use `Widget.loading` name - conflicts with Textual base (use `loading_repos`)
- **Don't** loop variable shadow outer scope (mypy catches)
- **Don't** commit or stage changes without explicit user request
- **Don't** modify config without updating `EnvironmentManager` flow

## COMMANDS

```bash
# Development
uv sync                              # Install deps
uv run qdpi --help                   # Run CLI
uv run python -m qdpi                # Alternative entry

# Quality
uv run ruff check src/qdpi           # Lint
uv run mypy src/qdpi                 # Type check (strict)
uv run pytest tests/                 # Test (stub only)

# Usage
qdpi init                            # Create ~/.config/qdpi/config.yaml
qdpi create my-feature -r backend:feat/x -r frontend:main
qdpi list --json                     # JSON output
qdpi delete my-feature --force       # Skip safety checks
```

## NOTES

- Config lives at `~/.config/qdpi/config.yaml` (XDG_CONFIG_HOME)
- Registry JSON at same location
- Worktrees reference base repos - deleting base breaks worktrees
- Branch not found? Callback `on_branch_not_found` prompts user
- TUI validates name with `is_valid_environment_name()` before proceeding
