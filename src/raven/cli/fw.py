"""raven fw — manage port forwarding."""

from __future__ import annotations

import logging
import typer

from raven.backends import get_backend
from raven.config.loader import load_config, save_config
from raven.config.schema import PortForward
from raven.state.store import load_state
from raven.util.console import console
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)

def fw_cmd(
    name: str = typer.Argument(..., help="Environment name."),
    mapping: str = typer.Argument(..., help="Port mapping (host_port:container_port, e.g. 8080:80)."),
    protocol: str = typer.Option("tcp", "--protocol", "-p", help="Protocol (tcp or udp)."),
    bind_host: str = typer.Option("127.0.0.1", "--bind", "-b", help="Host interface to bind to."),
) -> None:
    """Add a port forwarding mapping to an environment."""
    try:
        parts = mapping.split(":")
        if len(parts) != 2:
            raise ValueError("Invalid mapping format. Use host_port:container_port")
        host_port = int(parts[0])
        container_port = int(parts[1])
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        load_state(name)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Environment '{name}' not found.")
        raise typer.Exit(1)

    config_path = env_dir(name) / "config.yaml"
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error loading config:[/red] {exc}")
        raise typer.Exit(1)

    # Check if mapping already exists
    for pf in config.network.port_forwards:
        if pf.host == host_port and pf.protocol == protocol:
            console.print(f"[yellow]Port {host_port}/{protocol} is already forwarded.[/yellow]")
            raise typer.Exit(0)

    new_fw = PortForward(
        host=host_port,
        container=container_port,
        protocol=protocol, # type: ignore
        bind_host=bind_host
    )
    config.network.port_forwards.append(new_fw)
    save_config(config, config_path)

    # Update backend files (e.g. systemd units)
    backend = get_backend(config)
    try:
        # Some backends might need state to regenerate files
        state = load_state(name)
        if hasattr(backend, '_regenerate_service'): # Internal helper if we have it
             backend._regenerate_service(name)
        else:
            # For Podman, we can just call generate_container_service if we have access to it, 
            # or rely on the fact that start() does it.
            # But we want to update it NOW so the user just has to restart.
            from raven.backends.podman.systemd import generate_container_service
            if config.backend == "podman":
                generate_container_service(config, state.ssh_port)
                from raven.util.subprocess import run
                run(["systemctl", "--user", "daemon-reload"])
    except Exception as exc:
        log.warning("Could not automatically update backend service files: %s", exc)

    console.print(f"[green]Port forwarding {host_port} -> {container_port} ({protocol}) added to '{name}'.[/green]")
    console.print("[yellow]Warning:[/yellow] You must restart the environment to apply these changes:")
    console.print(f"  [cyan]raven restart {name}[/cyan]")
