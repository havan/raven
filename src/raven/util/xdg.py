"""XDG Base Directory helpers for raven state and config paths."""

from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """~/.local/share/raven/"""
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return Path(base) / "raven"


def config_dir() -> Path:
    """~/.config/raven/"""
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(base) / "raven"


def env_dir(name: str) -> Path:
    """~/.local/share/raven/envs/<name>/"""
    return data_dir() / "envs" / name


def nft_rules_dir() -> Path:
    """~/.local/share/raven/nft-rules/"""
    return data_dir() / "nft-rules"


def logs_dir() -> Path:
    """~/.local/share/raven/logs/"""
    return data_dir() / "logs"


def templates_dir() -> Path:
    """~/.local/share/raven/templates/"""
    return data_dir() / "templates"


def presets_dir() -> Path:
    """~/.local/share/raven/presets/"""
    return data_dir() / "presets"


def quadlet_dir() -> Path:
    """~/.config/containers/systemd/ (legacy Quadlet files)"""
    return Path.home() / ".config" / "containers" / "systemd"


def user_service_dir() -> Path:
    """~/.config/systemd/user/ (plain systemd user unit files)"""
    return Path.home() / ".config" / "systemd" / "user"


def git_root() -> Path:
    """Root directory for git clones. Reads RAVEN_GIT_ROOT env var, defaults to ~/git."""
    base = os.environ.get("RAVEN_GIT_ROOT", os.path.expanduser("~/git"))
    return Path(base)


def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    for d in [data_dir(), data_dir() / "envs", data_dir() / "networks",
              nft_rules_dir(), logs_dir(), templates_dir(), presets_dir(),
              quadlet_dir(), user_service_dir()]:
        d.mkdir(parents=True, exist_ok=True)
