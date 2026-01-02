"""Pydantic models for QDPI configuration."""

from pathlib import Path

from pydantic import BaseModel, field_validator


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


class Config(BaseModel):
    """Main QDPI configuration."""

    base_repos_dir: Path = Path("~/.local/share/qdpi/repos")
    environments_dir: Path = Path("~/qdpi-envs")
    repositories: dict[str, RepoConfig] = {}
    templates: list[TemplateConfig] = []
    copy_files: list[CopyFileConfig] = []
    symlinks: list[SymlinkConfig] = []

    @field_validator("base_repos_dir", "environments_dir", mode="before")
    @classmethod
    def expand_path(cls, v: str | Path) -> Path:
        """Expand ~ in paths."""
        return Path(v).expanduser()

    model_config = {"extra": "ignore"}
