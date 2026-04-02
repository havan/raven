"""State models for raven environments."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class EnvStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    UNKNOWN = "unknown"


class NetworkPhase(str, Enum):
    INSTALL = "install"
    RUN = "run"


class EnvState(BaseModel):
    """Persistent configuration state for an environment.

    Runtime state (running/stopped, uptime) is always queried live from the
    backend and is never stored here.
    """

    name: str
    container_id: str = ""
    network_phase: NetworkPhase = NetworkPhase.RUN
    ssh_port: int = 0
    install_completed: bool = False
    backend: str = "podman"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
