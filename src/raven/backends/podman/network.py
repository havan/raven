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
    result = run([
        "podman", "network", "create",
        "--ignore",
        "--label", f"raven.env={env_name}",
        "--label", "raven.managed=true",
        name,
    ], check=False)
    if result.returncode == 0:
        log.info("Created network: %s", name)
    else:
        log.debug("Network %s already exists", name)
    return name


def get_network_interface(env_name: str) -> str:
    """Return the bridge interface name Podman/netavark assigned to the network."""
    name = network_name(env_name)
    result = run(
        ["podman", "network", "inspect", "--format", "{{.NetworkInterface}}", name],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Cannot inspect network '{name}': {result.stderr.strip()}")
    iface = result.stdout.strip()
    if not iface:
        raise RuntimeError(f"No interface name returned for network '{name}'")
    return iface


def remove_network(env_name: str) -> None:
    """Remove the Podman network for an environment."""
    name = network_name(env_name)
    result = run(["podman", "network", "rm", "-f", name], check=False)
    if result.returncode == 0:
        log.info("Removed network: %s", name)
    else:
        log.warning("Failed to remove network %s: %s", name, result.stderr.strip())
