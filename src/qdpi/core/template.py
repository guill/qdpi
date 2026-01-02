"""Template engine for QDPI."""

from datetime import datetime
from pathlib import Path

from jinja2 import Environment as JinjaEnv, FileSystemLoader, TemplateError

from qdpi.config.models import TemplateConfig
from qdpi.registry.registry import RepoInstance, SymlinkEntry


class TemplateEngineError(Exception):
    """Raised when template rendering fails."""


class TemplateEngine:
    """Renders Jinja2 templates with environment context."""

    def __init__(self) -> None:
        """Initialize the template engine."""
        # Use a FileSystemLoader with root to allow absolute paths
        self.jinja_env = JinjaEnv(
            loader=FileSystemLoader("/"),
            autoescape=False,
            keep_trailing_newline=True,
        )

    def render(
        self,
        template_path: Path,
        env_name: str,
        repos: list[RepoInstance],
        symlinks: list[SymlinkEntry],
        env_path: Path,
    ) -> str:
        """
        Render a template with environment context.

        Args:
            template_path: Path to the Jinja2 template file.
            env_name: Name of the environment.
            repos: List of repository instances in the environment.
            symlinks: List of symlinks in the environment.
            env_path: Path to the environment directory.

        Returns:
            Rendered template content.

        Raises:
            TemplateEngineError: If rendering fails.
        """
        try:
            # Get template using absolute path (strip leading /)
            template_str = str(template_path.resolve())
            if template_str.startswith("/"):
                template_str = template_str[1:]
            template = self.jinja_env.get_template(template_str)

            # Build context
            context = {
                "env_name": env_name,
                "repos": [{"name": r.name, "branch": r.branch} for r in repos],
                "repo_names": {r.name for r in repos},
                "symlinks": [{"source": s.source, "target": s.target} for s in symlinks],
                "env_path": str(env_path),
                "created_at": datetime.now().isoformat(),
            }

            return template.render(**context)

        except TemplateError as e:
            raise TemplateEngineError(f"Failed to render template {template_path}: {e}") from e
        except FileNotFoundError as e:
            raise TemplateEngineError(f"Template not found: {template_path}") from e

    @staticmethod
    def should_render(template_config: TemplateConfig, repo_names: set[str]) -> bool:
        """
        Check if template should be rendered based on 'when' condition.

        Args:
            template_config: Template configuration.
            repo_names: Set of repository names in the environment.

        Returns:
            True if template should be rendered.
        """
        if template_config.when is None:
            return True
        return all(repo in repo_names for repo in template_config.when)
