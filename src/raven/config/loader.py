"""Load, validate, and save raven YAML configuration files."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from raven.config.schema import EnvConfig
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)

# Well-known config file names searched in the current directory
CONFIG_FILENAMES = ("raven.yaml", "raven.yml")


def load_config(path: Path | None = None) -> EnvConfig:
    """Load and validate an environment config from YAML.

    Args:
        path: Explicit path to a YAML file.  If None, searches the current
              directory for raven.yaml / raven.yml.

    Returns:
        A validated EnvConfig.

    Raises:
        FileNotFoundError: No config file found.
        ValueError: YAML parsing or validation failed.
    """
    if path is None:
        path = _find_config_in_cwd()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    log.info("Loading config from %s", path)
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Expected a YAML mapping in {path}, got {type(raw).__name__}")

    # Interpolate ${VAR} references in env_vars values
    if "env_vars" in raw and isinstance(raw["env_vars"], dict):
        raw["env_vars"] = {
            k: _interpolate_env(v) if isinstance(v, str) else v
            for k, v in raw["env_vars"].items()
        }

    try:
        return EnvConfig.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Invalid config in {path}:\n{exc}") from exc


def save_config(config: EnvConfig, path: Path | None = None) -> Path:
    """Save an EnvConfig to YAML.

    Args:
        config: The configuration to save.
        path: Where to write. Defaults to the env's state directory.

    Returns:
        The path written to.
    """
    if path is None:
        d = env_dir(config.name)
        d.mkdir(parents=True, exist_ok=True)
        path = d / "config.yaml"

    data = config.model_dump(mode="json")
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    log.info("Config saved to %s", path)
    return path


def _find_config_in_cwd() -> Path:
    """Search the current directory for a raven config file."""
    cwd = Path.cwd()
    for name in CONFIG_FILENAMES:
        candidate = cwd / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"No raven config found. Looked for: {', '.join(CONFIG_FILENAMES)} in {cwd}"
    )


def _interpolate_env(value: str) -> str:
    """Replace ${VAR} patterns with host environment variable values."""
    import re

    def _replace(match: re.Match[str]) -> str:
        var = match.group(1)
        res = os.environ.get(var)
        if res is None:
            log.warning("Environment variable ${%s} not found, using empty string", var)
            return ""
        return res

    return re.sub(r"\$\{([^}]+)\}", _replace, value)
