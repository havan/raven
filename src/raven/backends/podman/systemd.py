"""Generate Podman Quadlet .container and .network unit files."""

from __future__ import annotations

import logging
from pathlib import Path

from raven.config.schema import EnvConfig, SourceMount
from raven.util.xdg import quadlet_dir

log = logging.getLogger(__name__)

CONTAINER_PREFIX = "raven-"


def container_name(env_name: str) -> str:
    return f"{CONTAINER_PREFIX}{env_name}"


def network_name(env_name: str) -> str:
    return f"{CONTAINER_PREFIX}{env_name}"


def _quadlet_path(env_name: str, ext: str) -> Path:
    return quadlet_dir() / f"raven-{env_name}.{ext}"


def generate_network_quadlet(config: EnvConfig) -> Path:
    """Write the .network Quadlet file and return its path."""
    path = _quadlet_path(config.name, "network")
    content = f"""\
[Network]
NetworkName={network_name(config.name)}
Driver=bridge
Label=raven.env={config.name}
Label=raven.managed=true
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    log.info("Wrote network quadlet: %s", path)
    return path


def generate_container_quadlet(config: EnvConfig, ssh_port: int) -> Path:
    """Write the .container Quadlet file and return its path."""
    lines = [
        "[Unit]",
        f"Description=Raven dev environment: {config.name}",
        "After=network-online.target",
        "",
        "[Container]",
        f"Image={config.image}",
        f"ContainerName={container_name(config.name)}",
        f"Network=raven-{config.name}.network",
    ]

    # SSH port for VS Code remote
    lines.append(f"PublishPort=127.0.0.1:{ssh_port}:22")

    # User-configured port forwards
    for pf in config.network.port_forwards:
        lines.append(f"PublishPort={pf.bind_host}:{pf.host}:{pf.container}/{pf.protocol}")

    # Source volume mount
    if isinstance(config.source, SourceMount):
        lines.append(f"Volume={config.source.path}:{config.source.mount_path}:Z")

    # Environment variables
    for key, value in config.env_vars.items():
        lines.append(f"Environment={key}={value}")

    # Labels
    lines.append(f"Label=raven.env={config.name}")
    lines.append("Label=raven.managed=true")

    # Resource limits
    if config.resources.cpus > 0:
        lines.append(f"Cpus={config.resources.cpus}")
    if config.resources.memory != "0":
        lines.append(f"Memory={config.resources.memory}")

    # Keep container running
    lines.append("Exec=sleep infinity")

    # Service section
    lines.extend([
        "",
        "[Service]",
        "Restart=on-failure",
        "TimeoutStartSec=60",
        "",
        "[Install]",
        "WantedBy=default.target",
    ])

    path = _quadlet_path(config.name, "container")
    path.write_text("\n".join(lines) + "\n")
    log.info("Wrote container quadlet: %s", path)
    return path


def remove_quadlet_files(env_name: str) -> None:
    """Remove Quadlet files for an environment."""
    for ext in ("container", "network"):
        path = _quadlet_path(env_name, ext)
        if path.exists():
            path.unlink()
            log.info("Removed quadlet: %s", path)
