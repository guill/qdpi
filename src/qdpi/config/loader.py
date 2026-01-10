"""Configuration loader for QDPI."""

from pathlib import Path

import yaml

from qdpi.config.models import Config
from qdpi.utils.paths import get_config_dir

# Default config file locations
GLOBAL_CONFIG_PATH = get_config_dir() / "config.yaml"
LOCAL_CONFIG_NAME = ".qdpi.yaml"


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""


def find_config_file() -> Path | None:
    """
    Find the configuration file.

    Priority:
    1. Local .qdpi.yaml in current directory (completely overrides global)
    2. Global ~/.config/qdpi/config.yaml
    """
    # Check for local config first
    local_config = Path.cwd() / LOCAL_CONFIG_NAME
    if local_config.exists():
        return local_config

    # Fall back to global config
    if GLOBAL_CONFIG_PATH.exists():
        return GLOBAL_CONFIG_PATH

    return None


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file.

    Args:
        config_path: Explicit path to config file. If None, auto-discovers.

    Returns:
        Validated Config object.

    Raises:
        ConfigError: If config file is missing or invalid.
    """
    if config_path is None:
        config_path = find_config_file()

    if config_path is None:
        raise ConfigError(
            f"No configuration file found. Run 'qdpi init' to create one at {GLOBAL_CONFIG_PATH}"
        )

    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path) as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in config file: {e}") from e

    if raw_config is None:
        raw_config = {}

    try:
        return Config(**raw_config)
    except Exception as e:
        raise ConfigError(f"Invalid configuration: {e}") from e


def get_default_config() -> str:
    """Return the default configuration file content."""
    from qdpi.config.models import _default_base_repos_dir, _default_environments_dir

    base_repos = str(_default_base_repos_dir())
    envs_dir = str(_default_environments_dir())
    config_dir = str(get_config_dir())

    return f"""\
# QDPI Configuration
# https://github.com/your-org/qdpi

# Where base repositories are cloned (worktree sources)
# Default: {base_repos}
# base_repos_dir: {base_repos}

# Where environments are created
# Default: {envs_dir}
# environments_dir: {envs_dir}

# Repository definitions
# Key is the repository name (used in commands and templates)
repositories: {{}}
  # example:
  #   url: git@github.com:your-org/example-repo.git

# Jinja2 templates to render into environments
templates: []
  # - source: {config_dir}/templates/AGENTS.md.j2
  #   destination: AGENTS.md
  #   # Optional: only generate when these repos are present
  #   # when: [repo1, repo2]

# Static files to copy (no templating)
copy_files: []
  # - source: {config_dir}/files/.editorconfig
  #   destination: .editorconfig
  #   # Optional: only copy when these repos are present
  #   # when: [repo1]

# Symlinks to create between repositories
# Note: On Windows without Developer Mode, symlinks fall back to copying
symlinks: []
  # - source: repo1/shared_module
  #   target: repo2/src/shared_module
  #   when: [repo1, repo2]  # Required: repos that must be present
"""


def init_config(force: bool = False) -> Path:
    """
    Create default configuration file.

    Args:
        force: Overwrite existing config file.

    Returns:
        Path to created config file.

    Raises:
        ConfigError: If config exists and force is False.
    """
    if GLOBAL_CONFIG_PATH.exists() and not force:
        raise ConfigError(
            f"Configuration file already exists at {GLOBAL_CONFIG_PATH}. Use --force to overwrite."
        )

    # Create config directory
    GLOBAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Create templates directory
    templates_dir = GLOBAL_CONFIG_PATH.parent / "templates"
    templates_dir.mkdir(exist_ok=True)

    # Write default config
    GLOBAL_CONFIG_PATH.write_text(get_default_config())

    return GLOBAL_CONFIG_PATH
