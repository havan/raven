"""Backend registry — maps BackendType to implementation classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raven.config.schema import BackendType

if TYPE_CHECKING:
    from raven.backends.base import Backend
    from raven.config.schema import EnvConfig


def get_backend(config_or_type: EnvConfig | BackendType | str) -> Backend:
    """Return the appropriate Backend instance for the given config or backend type."""
    from raven.config.schema import EnvConfig
    if isinstance(config_or_type, EnvConfig):
        backend_type = config_or_type.backend
    else:
        backend_type = config_or_type

    if backend_type == BackendType.PODMAN:
        from raven.backends.podman.backend import PodmanBackend
        return PodmanBackend()
    elif backend_type == BackendType.FIRECRACKER:
        from raven.backends.firecracker.backend import FirecrackerBackend
        return FirecrackerBackend()
    else:
        raise ValueError(f"Unknown backend: {backend_type}")
