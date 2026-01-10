"""Pydantic models for QDPI configuration."""

from pathlib import Path

from pydantic import BaseModel, field_validator

from qdpi.utils.paths import get_data_dir


class RepoConfig(BaseModel):
    """Configuration for a single repository."""

    url: str


class TemplateConfig(BaseModel):
    """Configuration for a Jinja2 template."""

    source: Path
    destination: str
    when: list[str] | None = None

    @field_validator("source", mode="before")
    @classmethod
    def expand_source_path(cls, v: str | Path) -> Path:
        """Expand ~ in source path."""
        return Path(v).expanduser()


class CopyFileConfig(BaseModel):
    """Configuration for a static file to copy."""

    source: Path
    destination: str
    when: list[str] | None = None

    @field_validator("source", mode="before")
    @classmethod
    def expand_source_path(cls, v: str | Path) -> Path:
        """Expand ~ in source path."""
        return Path(v).expanduser()


class SymlinkConfig(BaseModel):
    """Configuration for a symlink between repositories."""

    source: str  # Relative to environment root
    target: str  # Relative to environment root
    when: list[str]


def _default_base_repos_dir() -> Path:
    """Get the default base repos directory (platform-specific)."""
    return get_data_dir() / "repos"


def _default_environments_dir() -> Path:
    """Get the default environments directory."""
    return Path.home() / "qdpi-envs"


class Config(BaseModel):
    """Main QDPI configuration."""

    base_repos_dir: Path = Path()  # Set in validator if empty
    environments_dir: Path = Path()  # Set in validator if empty
    repositories: dict[str, RepoConfig] = {}
    templates: list[TemplateConfig] = []
    copy_files: list[CopyFileConfig] = []
    symlinks: list[SymlinkConfig] = []

    @field_validator("base_repos_dir", mode="before")
    @classmethod
    def expand_base_repos_path(cls, v: str | Path | None) -> Path:
        """Expand ~ in paths or use platform-specific default."""
        if v is None or (isinstance(v, Path) and str(v) == "."):
            return _default_base_repos_dir()
        return Path(v).expanduser()

    @field_validator("environments_dir", mode="before")
    @classmethod
    def expand_environments_path(cls, v: str | Path | None) -> Path:
        """Expand ~ in paths or use platform-specific default."""
        if v is None or (isinstance(v, Path) and str(v) == "."):
            return _default_environments_dir()
        return Path(v).expanduser()

    model_config = {"extra": "ignore"}
