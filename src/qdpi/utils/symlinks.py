"""Cross-platform symlink utilities with Windows elevation support."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == "win32"


def create_symlink_elevated(source: Path, target: Path) -> bool:
    """
    Create a symlink using an elevated PowerShell process on Windows.

    Args:
        source: The source path (what the symlink points to).
        target: The target path (where the symlink is created).

    Returns:
        True if symlink was created successfully, False otherwise.
    """
    if not is_windows():
        return False

    # PowerShell command to create the symlink
    # Using New-Item with -ItemType SymbolicLink
    ps_command = (
        f'New-Item -ItemType SymbolicLink -Path "{target}" -Target "{source}" -Force'
    )

    try:
        # Use PowerShell's Start-Process with -Verb RunAs to trigger UAC elevation
        # The -Wait flag makes it synchronous, -PassThru lets us check the result
        result = subprocess.run(
            [
                "powershell",
                "-Command",
                f'Start-Process powershell -ArgumentList \'-Command {ps_command}\' '
                f"-Verb RunAs -Wait",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        # Check if the symlink was created
        return target.is_symlink()

    except Exception:
        return False


def prompt_and_create_symlink_elevated(
    source: Path,
    target: Path,
    prompt_callback: Callable[[str], bool] | None = None,
) -> bool:
    """
    Prompt the user and attempt to create a symlink with elevation.

    Args:
        source: The source path (what the symlink points to).
        target: The target path (where the symlink is created).
        prompt_callback: Optional callback to prompt user. If None, uses typer.confirm.
            Signature: (message: str) -> bool

    Returns:
        True if symlink was created, False if user declined or creation failed.
    """
    if prompt_callback is None:
        import typer

        def default_prompt(msg: str) -> bool:
            return typer.confirm(msg)

        prompt_callback = default_prompt

    message = (
        f"Symlink creation requires elevation on Windows.\n"
        f"  {target} -> {source}\n"
        f"Allow Windows to prompt for administrator access?"
    )

    if not prompt_callback(message):
        return False

    return create_symlink_elevated(source, target)
