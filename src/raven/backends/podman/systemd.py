"""Generate plain systemd .service unit files for Podman containers."""

from __future__ import annotations

import logging
from pathlib import Path

from raven.config.schema import EnvConfig, SourceMount
from raven.util.xdg import quadlet_dir, user_service_dir

log = logging.getLogger(__name__)

CONTAINER_PREFIX = "raven-"


def container_name(env_name: str) -> str:
    return f"{CONTAINER_PREFIX}{env_name}"


def network_name(env_name: str) -> str:
    return f"systemd-{CONTAINER_PREFIX}{env_name}"


def _service_path(env_name: str) -> Path:
    return user_service_dir() / f"raven-{env_name}.service"


def generate_container_service(config: EnvConfig, ssh_port: int) -> Path:
    """Write a plain systemd .service file for the container and return its path."""
    cname = container_name(config.name)
    nname = network_name(config.name)

    run_args = [
        f"--name={cname}",
        f"--network={nname}",
        f"--publish=127.0.0.1:{ssh_port}:22",
    ]

    for pf in config.network.port_forwards:
        run_args.append(f"--publish={pf.bind_host}:{pf.host}:{pf.container}/{pf.protocol}")

    if isinstance(config.source, SourceMount):
        run_args.append(f"--volume={config.source.path}:{config.source.mount_path}:Z")

    for key, value in config.env_vars.items():
        run_args.append(f"--env={key}={value}")

    run_args.append(f"--label=raven.env={config.name}")
    run_args.append("--label=raven.managed=true")

    if config.resources.cpus > 0:
        run_args.append(f"--cpus={config.resources.cpus}")
    if config.resources.memory != "0":
        run_args.append(f"--memory={config.resources.memory}")

    run_args.append(config.image)
    run_args.append("sleep infinity")

    exec_start = "/usr/bin/podman run " + " ".join(run_args)

    content = f"""\
[Unit]
Description=Raven dev environment: {config.name}
After=network-online.target

[Service]
ExecStartPre=-/usr/bin/podman rm -f {cname}
ExecStart={exec_start}
ExecStop=/usr/bin/podman stop {cname}
Restart=on-failure
TimeoutStartSec=60
TimeoutStopSec=30
Type=simple

[Install]
WantedBy=default.target
"""
    path = _service_path(config.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    log.info("Wrote service unit: %s", path)
    return path


def remove_service_files(env_name: str) -> None:
    """Remove the service unit file and any legacy Quadlet files for an environment."""
    service = _service_path(env_name)
    if service.exists():
        service.unlink()
        log.info("Removed service unit: %s", service)

    # Clean up legacy Quadlet files if they exist
    for ext in ("container", "network"):
        legacy = quadlet_dir() / f"raven-{env_name}.{ext}"
        if legacy.exists():
            legacy.unlink()
            log.info("Removed legacy quadlet file: %s", legacy)
