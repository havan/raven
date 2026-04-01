"""Backend registry — maps BackendType to implementation classes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from raven.config.schema import BackendType

if TYPE_CHECKING:
    from raven.backends.base import Backend
    from raven.config.schema import EnvConfig


def get_backend(config: EnvConfig) -> Backend:
    """Return the appropriate Backend instance for the given config."""
    if config.backend == BackendType.PODMAN:
        from raven.backends.podman.backend import PodmanBackend
        return PodmanBackend()
    elif config.backend == BackendType.FIRECRACKER:
        from raven.backends.firecracker.backend import FirecrackerBackend
        return FirecrackerBackend()
    else:
        raise ValueError(f"Unknown backend: {config.backend}")
