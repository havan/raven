"""Read/write environment state from ~/.local/share/raven/envs/<name>/state.json."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from raven.state.models import EnvState
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)


def _state_path(name: str) -> Path:
    return env_dir(name) / "state.json"


def load_state(name: str) -> EnvState:
    """Load state for an environment, or raise FileNotFoundError."""
    path = _state_path(name)
    if not path.exists():
        raise FileNotFoundError(f"No state found for environment '{name}' at {path}")
    data = json.loads(path.read_text())
    return EnvState.model_validate(data)


def save_state(state: EnvState) -> Path:
    """Persist state to disk atomically."""
    import os
    import tempfile

    path = _state_path(state.name)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write via temporary file
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix="state.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(state.model_dump_json(indent=2) + "\n")
            f.flush()
            os.fsync(fd)
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    log.debug("State saved: %s", path)
    return path


def state_exists(name: str) -> bool:
    """Check whether state exists for the given environment name."""
    return _state_path(name).exists()


def delete_state(name: str) -> None:
    """Remove state file and the env directory if empty."""
    path = _state_path(name)
    if path.exists():
        path.unlink()
        log.debug("Deleted state: %s", path)
    # Remove all files and symlinks in the env directory, then rmdir if empty
    d = env_dir(name)
    if d.exists():
        for child in d.iterdir():
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
        try:
            d.rmdir()
        except OSError:
            pass  # directory not empty — leave it


def list_env_names() -> list[str]:
    """Return names of all environments that have state on disk."""
    envs_root = env_dir("")  # ~/.local/share/raven/envs/
    if not envs_root.exists():
        return []
    return sorted(
        d.name for d in envs_root.iterdir()
        if d.is_dir() and (d / "state.json").exists()
    )
