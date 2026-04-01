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


def quadlet_dir() -> Path:
    """~/.config/containers/systemd/"""
    return Path.home() / ".config" / "containers" / "systemd"


def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    for d in [data_dir(), data_dir() / "envs", data_dir() / "networks",
              nft_rules_dir(), logs_dir(), quadlet_dir()]:
        d.mkdir(parents=True, exist_ok=True)
