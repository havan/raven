"""Podman network creation and teardown helpers."""

from __future__ import annotations

import logging

from raven.backends.podman.systemd import network_name
from raven.util.subprocess import run

log = logging.getLogger(__name__)


def ensure_network(env_name: str) -> str:
    """Create the Podman network for an environment if it doesn't exist.

    Returns the network name.
    """
    name = network_name(env_name)
    result = run(["podman", "network", "exists", name], check=False)
    if result.returncode == 0:
        log.debug("Network %s already exists", name)
        return name

    run([
        "podman", "network", "create",
        "--label", f"raven.env={env_name}",
        "--label", "raven.managed=true",
        name,
    ])
    log.info("Created network: %s", name)
    return name


def remove_network(env_name: str) -> None:
    """Remove the Podman network for an environment."""
    name = network_name(env_name)
    run(["podman", "network", "rm", "-f", name], check=False)
    log.info("Removed network: %s", name)
