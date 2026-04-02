"""Pydantic models for raven environment configuration (YAML schema)."""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator

from raven.config.defaults import DEFAULT_PURGE_DIRS, DEFAULT_REGISTRIES


class BackendType(str, Enum):
    PODMAN = "podman"
    FIRECRACKER = "firecracker"


# ── Source ──────────────────────────────────────────────────────────────

class SourceMount(BaseModel):
    type: Literal["mount"]
    path: str
    mount_path: str = "/workspace"


class SourceClone(BaseModel):
    type: Literal["clone"]
    url: str
    ref: str = "main"
    mount_path: str = "/workspace"


Source = Annotated[Union[SourceMount, SourceClone], Field(discriminator="type")]


# ── Network ─────────────────────────────────────────────────────────────

class PortForward(BaseModel):
    host: int
    container: int
    protocol: Literal["tcp", "udp"] = "tcp"
    bind_host: str = "127.0.0.1"


class InstallPhaseNetwork(BaseModel):
    allowed_registries: list[str] = Field(default_factory=lambda: list(DEFAULT_REGISTRIES))
    allow_dns: bool = True


class RunPhaseNetwork(BaseModel):
    policy: Literal["open", "allowlist", "block"] = "open"
    allowed_hosts: list[str] = Field(default_factory=list)


class NetworkConfig(BaseModel):
    install_phase: InstallPhaseNetwork = Field(default_factory=InstallPhaseNetwork)
    run_phase: RunPhaseNetwork = Field(default_factory=RunPhaseNetwork)
    port_forwards: list[PortForward] = Field(default_factory=list)


# ── Resources ───────────────────────────────────────────────────────────

class ResourceLimits(BaseModel):
    cpus: float = 0.0    # 0 = no limit
    memory: str = "0"    # "0" = no limit; otherwise "4g", "512m", etc.


# ── VS Code ─────────────────────────────────────────────────────────────

class VSCodeConfig(BaseModel):
    extensions: list[str] = Field(default_factory=list)
    settings: dict[str, object] = Field(default_factory=dict)


# ── Reinstall ───────────────────────────────────────────────────────────

class ReinstallConfig(BaseModel):
    purge_dirs: list[str] = Field(default_factory=lambda: list(DEFAULT_PURGE_DIRS))
    commands: list[str] = Field(default_factory=list)  # falls back to setup_commands


# ── Top-level EnvConfig ─────────────────────────────────────────────────

ENV_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class EnvConfig(BaseModel):
    name: str
    version: int = 1
    backend: BackendType = BackendType.PODMAN
    image: str = "mcr.microsoft.com/devcontainers/base:ubuntu"
    source: Source
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    env_vars: dict[str, str] = Field(default_factory=dict)
    resources: ResourceLimits = Field(default_factory=ResourceLimits)
    setup_commands: list[str] = Field(default_factory=list)
    reinstall: ReinstallConfig = Field(default_factory=ReinstallConfig)
    vscode: VSCodeConfig = Field(default_factory=VSCodeConfig)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not ENV_NAME_RE.match(v):
            raise ValueError(
                f"Environment name '{v}' is invalid. "
                "Use only lowercase letters, digits, hyphens, and underscores. "
                "Must start with a letter or digit."
            )
        return v
