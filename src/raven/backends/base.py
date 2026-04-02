"""Abstract backend interface for raven environment engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from raven.config.schema import EnvConfig, VSCodeConfig
from raven.state.models import EnvStatus, NetworkPhase


@dataclass
class EnvInfo:
    """Summary information about an environment."""

    name: str
    status: EnvStatus
    backend: str
    image: str
    created_at: str
    ports: list[str] = field(default_factory=list)
    cpu_usage: str = ""
    memory_usage: str = ""
    source: str = ""


class Backend(ABC):
    """Abstract interface that all environment backends must implement.

    Each method is synchronous and may invoke subprocesses internally.
    """

    @abstractmethod
    def create(self, config: EnvConfig) -> str:
        """Create the environment (do NOT start it). Returns a backend-specific ID."""

    @abstractmethod
    def start(self, name: str) -> None:
        """Start a stopped or newly created environment."""

    @abstractmethod
    def stop(self, name: str, timeout: int = 10) -> None:
        """Gracefully stop a running environment."""

    @abstractmethod
    def destroy(self, name: str) -> None:
        """Stop and permanently remove the environment and its resources."""

    @abstractmethod
    def exec(
        self,
        name: str,
        command: list[str],
        *,
        workdir: str | None = None,
        user: str | None = None,
        env: dict[str, str] | None = None,
        tty: bool = False,
        interactive: bool = False,
    ) -> int:
        """Run a command inside the environment. Returns exit code."""

    @abstractmethod
    def shell(self, name: str, shell_binary: str = "/bin/bash") -> int:
        """Open an interactive shell inside the environment."""

    @abstractmethod
    def status(self, name: str) -> EnvStatus:
        """Query current status of the environment."""

    @abstractmethod
    def list_all(self) -> list[EnvInfo]:
        """List all raven-managed environments."""

    @abstractmethod
    def get_info(self, name: str) -> EnvInfo:
        """Get detailed info about a specific environment."""

    @abstractmethod
    def apply_network_phase(self, name: str, phase: NetworkPhase) -> None:
        """Switch nftables rules between install and run phases."""

    @abstractmethod
    def setup_vscode(self, name: str, config: VSCodeConfig) -> dict[str, str]:
        """Prepare VS Code remote access. Returns connection details."""

    @abstractmethod
    def launch_vscode(self, name: str, workspace: str) -> None:
        """Launch VS Code connected to the environment."""

    @abstractmethod
    def get_processes(self, name: str) -> dict[str, Any]:
        """Get live process list and resource usage.

        Returns a dict with 'processes' (list of dicts) and 'resources' (dict).
        """
