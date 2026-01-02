"""Environment registry for QDPI."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from qdpi.utils.paths import get_registry_path, ensure_data_dir


@dataclass
class RepoInstance:
    """A repository within an environment."""

    name: str
    branch: str
    worktree_path: str  # Stored as string for JSON serialization

    @property
    def path(self) -> Path:
        """Get worktree path as Path object."""
        return Path(self.worktree_path)


@dataclass
class SymlinkEntry:
    """A symlink within an environment."""

    source: str  # Relative to environment root
    target: str  # Relative to environment root


@dataclass
class Environment:
    """A development environment."""

    name: str
    path: str  # Stored as string for JSON serialization
    created_at: str  # ISO format string
    repos: list[RepoInstance] = field(default_factory=list)
    generated_files: list[str] = field(default_factory=list)
    symlinks: list[SymlinkEntry] = field(default_factory=list)

    @property
    def env_path(self) -> Path:
        """Get environment path as Path object."""
        return Path(self.path)

    @property
    def created_datetime(self) -> datetime:
        """Get created_at as datetime object."""
        return datetime.fromisoformat(self.created_at)

    @classmethod
    def create(
        cls,
        name: str,
        path: Path,
        repos: list[RepoInstance],
        generated_files: list[str],
        symlinks: list[SymlinkEntry],
    ) -> "Environment":
        """Create a new Environment with current timestamp."""
        return cls(
            name=name,
            path=str(path),
            created_at=datetime.now().isoformat(),
            repos=repos,
            generated_files=generated_files,
            symlinks=symlinks,
        )


@dataclass
class Registry:
    """Registry of all environments."""

    version: int = 1
    environments: dict[str, Environment] = field(default_factory=dict)


class RegistryError(Exception):
    """Raised when registry operations fail."""


class EnvironmentRegistry:
    """Manages the environment registry."""

    def __init__(self, registry_path: Path | None = None):
        """Initialize the registry."""
        self._registry_path = registry_path or get_registry_path()
        self._registry: Registry | None = None

    @property
    def registry_path(self) -> Path:
        """Get the registry file path."""
        return self._registry_path

    def _load(self) -> Registry:
        """Load the registry from disk."""
        if not self._registry_path.exists():
            return Registry()

        try:
            with open(self._registry_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise RegistryError(f"Failed to load registry: {e}") from e

        # Parse environments
        environments = {}
        for name, env_data in data.get("environments", {}).items():
            repos = [RepoInstance(**r) for r in env_data.get("repos", [])]
            symlinks = [SymlinkEntry(**s) for s in env_data.get("symlinks", [])]
            environments[name] = Environment(
                name=env_data["name"],
                path=env_data["path"],
                created_at=env_data["created_at"],
                repos=repos,
                generated_files=env_data.get("generated_files", []),
                symlinks=symlinks,
            )

        return Registry(version=data.get("version", 1), environments=environments)

    def _save(self, registry: Registry) -> None:
        """Save the registry to disk."""
        ensure_data_dir()

        data = {
            "version": registry.version,
            "environments": {name: asdict(env) for name, env in registry.environments.items()},
        }

        try:
            with open(self._registry_path, "w") as f:
                json.dump(data, f, indent=2)
        except OSError as e:
            raise RegistryError(f"Failed to save registry: {e}") from e

    def _get_registry(self) -> Registry:
        """Get the registry, loading if necessary."""
        if self._registry is None:
            self._registry = self._load()
        return self._registry

    def exists(self, name: str) -> bool:
        """Check if an environment exists in the registry."""
        return name in self._get_registry().environments

    def get(self, name: str) -> Environment:
        """
        Get an environment by name.

        Raises:
            RegistryError: If environment doesn't exist.
        """
        registry = self._get_registry()
        if name not in registry.environments:
            raise RegistryError(f"Environment '{name}' not found")
        return registry.environments[name]

    def add(self, environment: Environment) -> None:
        """
        Add an environment to the registry.

        Raises:
            RegistryError: If environment already exists.
        """
        registry = self._get_registry()
        if environment.name in registry.environments:
            raise RegistryError(f"Environment '{environment.name}' already exists")

        registry.environments[environment.name] = environment
        self._save(registry)

    def remove(self, name: str) -> None:
        """
        Remove an environment from the registry.

        Raises:
            RegistryError: If environment doesn't exist.
        """
        registry = self._get_registry()
        if name not in registry.environments:
            raise RegistryError(f"Environment '{name}' not found")

        del registry.environments[name]
        self._save(registry)

    def list_all(self) -> list[Environment]:
        """List all environments."""
        return list(self._get_registry().environments.values())

    def list_names(self) -> list[str]:
        """List all environment names."""
        return list(self._get_registry().environments.keys())

    def refresh(self) -> None:
        """Force reload from disk."""
        self._registry = None
