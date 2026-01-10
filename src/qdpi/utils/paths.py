"""Path utilities for QDPI."""

import re
from pathlib import Path

import platformdirs

APP_NAME = "qdpi"
APP_AUTHOR = "qdpi"


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
    """
    Get the QDPI data directory.

    Platform-specific:
    - Windows: %LOCALAPPDATA%/qdpi
    - macOS: ~/Library/Application Support/qdpi
    - Linux: ~/.local/share/qdpi
    """
    return Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR))


def get_config_dir() -> Path:
    """
    Get the QDPI config directory.

    Platform-specific:
    - Windows: %APPDATA%/qdpi
    - macOS: ~/Library/Application Support/qdpi
    - Linux: ~/.config/qdpi
    """
    return Path(platformdirs.user_config_dir(APP_NAME, APP_AUTHOR))


def get_registry_path() -> Path:
    """Get the path to the environment registry file."""
    return get_data_dir() / "registry.json"


def ensure_data_dir() -> Path:
    """Ensure the data directory exists and return its path."""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
