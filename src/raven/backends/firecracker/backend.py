"""Firecracker microVM backend — stub for future implementation."""

from __future__ import annotations

from raven.backends.base import Backend, EnvInfo
from raven.config.schema import EnvConfig, VSCodeConfig
from raven.state.models import EnvStatus, NetworkPhase

_NOT_IMPLEMENTED = "Firecracker backend is not yet implemented. Use backend: podman"


class FirecrackerBackend(Backend):
    def create(self, config: EnvConfig) -> str:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def start(self, name: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def stop(self, name: str, timeout: int = 10) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def destroy(self, name: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def exec(self, name: str, command: list[str], **kwargs) -> int:  # type: ignore[override]
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def shell(self, name: str, shell_binary: str = "/bin/bash") -> int:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def status(self, name: str) -> EnvStatus:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def list_all(self) -> list[EnvInfo]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_info(self, name: str) -> EnvInfo:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def apply_network_phase(self, name: str, phase: NetworkPhase) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def setup_vscode(self, name: str, config: VSCodeConfig) -> dict[str, str]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def launch_vscode(self, name: str, workspace: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def get_processes(self, name: str) -> dict[str, Any]:
        raise NotImplementedError(_NOT_IMPLEMENTED)
