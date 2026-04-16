"""Pydantic models for raven environment configuration (YAML schema)."""

from __future__ import annotations

import re
from enum import Enum
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

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


class NetworkConfig(BaseModel):
    policy: str = "open"
    allowed_hosts: list[str] = Field(default_factory=list)
    port_forwards: list[PortForward] = Field(default_factory=list)

    @field_validator("policy", mode="before")
    @classmethod
    def normalize_policy(cls, v: object) -> object:
        if isinstance(v, str):
            return {"allowlist": "restricted", "block": "offline"}.get(v, v)
        return v


# ── Resources ───────────────────────────────────────────────────────────

class ResourceLimits(BaseModel):
    cpus: float = 0.0    # 0 = no limit
    memory: str = "0"    # "0" = no limit; otherwise "4g", "512m", etc.


# ── VS Code ─────────────────────────────────────────────────────────────

class VSCodeConfig(BaseModel):
    extensions: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)


# ── Purge ──────────────────────────────────────────────────────────────

class PurgeConfig(BaseModel):
    purge_dirs: list[str] = Field(default_factory=lambda: list(DEFAULT_PURGE_DIRS))


# ── Build ───────────────────────────────────────────────────────────────

class BuildConfig(BaseModel):
    dockerfile: str = "Dockerfile"
    context: str = "."


# ── Top-level EnvConfig ─────────────────────────────────────────────────

ENV_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class EnvConfig(BaseModel):
    name: str
    version: int = 1
    backend: BackendType = BackendType.PODMAN
    image: Optional[str] = None
    build: Optional[BuildConfig] = None
    source: Source
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    env_vars: dict[str, str] = Field(default_factory=dict)
    resources: ResourceLimits = Field(default_factory=ResourceLimits)
    setup_commands: list[str] = Field(default_factory=list)
    purge: PurgeConfig = Field(default_factory=PurgeConfig)
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

    @model_validator(mode="after")
    def validate_image_or_build(self) -> EnvConfig:
        if not self.image and not self.build:
            raise ValueError("Either 'image' or 'build' must be specified in the configuration.")
        return self
