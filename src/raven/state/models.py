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
    """Mutable runtime state persisted to state.json."""

    name: str
    container_id: str = ""
    status: EnvStatus = EnvStatus.CREATED
    network_phase: NetworkPhase = NetworkPhase.RUN
    network_name: str = ""
    network_interface: str = ""  # actual bridge interface name assigned by Podman/netavark
    ssh_port: int = 0
    install_completed: bool = False
    backend: str = "podman"
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    started_at: str = ""
