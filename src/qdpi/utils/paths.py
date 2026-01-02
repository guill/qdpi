"""Path utilities for QDPI."""

import re
from pathlib import Path


def is_valid_environment_name(name: str) -> bool:
    """
    Check if a name is valid for an environment.

    Valid names:
    - Only letters, numbers, hyphens, underscores
    - Cannot start with a hyphen or dot
    - Cannot be empty
    """
    if not name:
        return False

    # Must be a valid directory name
    pattern = r"^[a-zA-Z0-9_][a-zA-Z0-9_-]*$"
    return bool(re.match(pattern, name))


def get_data_dir() -> Path:
    """Get the QDPI data directory (~/.local/share/qdpi)."""
    return Path("~/.local/share/qdpi").expanduser()


def get_config_dir() -> Path:
    """Get the QDPI config directory (~/.config/qdpi)."""
    return Path("~/.config/qdpi").expanduser()


def get_registry_path() -> Path:
    """Get the path to the environment registry file."""
    return get_data_dir() / "registry.json"


def ensure_data_dir() -> Path:
    """Ensure the data directory exists and return its path."""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
