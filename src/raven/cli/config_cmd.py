"""raven config — CLI porcelain for modifying environment configuration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from raven.backends.podman.systemd import generate_container_service
from raven.config.loader import load_config, save_config
from raven.config.schema import EnvConfig, PortForward
from raven.state.models import EnvStatus
from raven.state.store import load_state, state_exists
from raven.util.console import console
from raven.util.subprocess import run
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)

config_app = typer.Typer(
    name="config",
    help="Manage environment configuration.",
    no_args_is_help=True,
)


def _regenerate_unit(name: str, cfg: EnvConfig) -> None:
    """Regenerate the systemd service unit, reload the daemon, and warn if restart is needed."""
    if not state_exists(name):
        return
    state = load_state(name)
    generate_container_service(cfg, state.ssh_port)
    run(["systemctl", "--user", "daemon-reload"])
    if state.status == EnvStatus.RUNNING:
        console.print(
            f"[yellow]Container is running — restart required to apply changes:[/yellow] "
            f"[bold]raven restart {name}[/bold]"
        )


def _load(name: str) -> tuple[EnvConfig, Path]:
    path = env_dir(name) / "config.yaml"
    if not path.exists():
        console.print(f"[red]Error:[/red] No config found for environment '{name}' at {path}")
        raise typer.Exit(1)
    return load_config(path), path


@config_app.command(name="show")
def config_show(
    name: str = typer.Argument(help="Environment name."),
) -> None:
    """Show the current configuration for an environment."""
    import yaml
    cfg, path = _load(name)
    data = cfg.model_dump(mode="json")
    console.print(f"[dim]# {path}[/dim]")
    console.print(yaml.dump(data, default_flow_style=False, sort_keys=False))


@config_app.command(name="env")
def config_env(
    name: str = typer.Argument(help="Environment name."),
    assignments: list[str] = typer.Argument(help="KEY=VALUE pairs to set."),
) -> None:
    """Add or update environment variables.

    Example: raven config env myapp DEBUG=1 PORT=8080
    """
    if not assignments:
        console.print("[yellow]No KEY=VALUE pairs provided.[/yellow]")
        raise typer.Exit(1)

    parsed: dict[str, str] = {}
    for item in assignments:
        if "=" not in item:
            console.print(f"[red]Error:[/red] Invalid format '{item}' — expected KEY=VALUE")
            raise typer.Exit(1)
        key, _, value = item.partition("=")
        key = key.strip()
        if not key:
            console.print(f"[red]Error:[/red] Empty key in '{item}'")
            raise typer.Exit(1)
        parsed[key] = value

    cfg, path = _load(name)
    cfg.env_vars.update(parsed)
    save_config(cfg, path)
    _regenerate_unit(name, cfg)

    for k, v in parsed.items():
        console.print(f"  [cyan]{k}[/cyan] = {v}")
    console.print(f"[green]Updated env_vars for '{name}'.[/green]")


@config_app.command(name="ports")
def config_ports(
    name: str = typer.Argument(help="Environment name."),
    action: str = typer.Argument(help="Action: add or remove."),
    mapping: str = typer.Argument(help="Port mapping HOST:CONTAINER or HOST:CONTAINER/PROTOCOL, e.g. 8080:80 or 5432:5432/tcp."),
) -> None:
    """Manage port forwards.

    Examples:
      raven config ports myapp add 8080:80
      raven config ports myapp add 5432:5432/tcp
      raven config ports myapp remove 8080:80
    """
    action = action.lower()
    if action not in ("add", "remove"):
        console.print(f"[red]Error:[/red] Action must be 'add' or 'remove', got '{action}'")
        raise typer.Exit(1)

    # Parse HOST:CONTAINER[/protocol]
    if ":" not in mapping:
        console.print(f"[red]Error:[/red] Invalid mapping '{mapping}' — expected HOST:CONTAINER or HOST:CONTAINER/PROTOCOL")
        raise typer.Exit(1)

    host_str, _, container_part = mapping.partition(":")
    protocol = "tcp"
    if "/" in container_part:
        container_str, _, protocol = container_part.partition("/")
        protocol = protocol.lower()
    else:
        container_str = container_part

    try:
        host_port = int(host_str)
        container_port = int(container_str)
    except ValueError:
        console.print(f"[red]Error:[/red] Ports must be integers, got '{host_str}:{container_str}'")
        raise typer.Exit(1)

    if protocol not in ("tcp", "udp"):
        console.print(f"[red]Error:[/red] Protocol must be 'tcp' or 'udp', got '{protocol}'")
        raise typer.Exit(1)

    cfg, path = _load(name)

    if action == "add":
        # Check for duplicate
        for pf in cfg.network.port_forwards:
            if pf.host == host_port and pf.container == container_port and pf.protocol == protocol:
                console.print(f"[yellow]Port forward {host_port}:{container_port}/{protocol} already exists.[/yellow]")
                raise typer.Exit()
        cfg.network.port_forwards.append(
            PortForward(host=host_port, container=container_port, protocol=protocol)  # type: ignore[arg-type]
        )
        save_config(cfg, path)
        _regenerate_unit(name, cfg)
        console.print(f"[green]Added port forward {host_port}:{container_port}/{protocol} to '{name}'.[/green]")

    else:  # remove
        before = len(cfg.network.port_forwards)
        cfg.network.port_forwards = [
            pf for pf in cfg.network.port_forwards
            if not (pf.host == host_port and pf.container == container_port and pf.protocol == protocol)
        ]
        if len(cfg.network.port_forwards) == before:
            console.print(f"[yellow]No matching port forward {host_port}:{container_port}/{protocol} found.[/yellow]")
            raise typer.Exit(1)
        save_config(cfg, path)
        _regenerate_unit(name, cfg)
        console.print(f"[green]Removed port forward {host_port}:{container_port}/{protocol} from '{name}'.[/green]")


@config_app.command(name="resources")
def config_resources(
    name: str = typer.Argument(help="Environment name."),
    memory: Optional[str] = typer.Option(None, "--memory", "-m", help="Memory limit (e.g. 4g, 512m). Use '0' for no limit."),
    cpus: Optional[float] = typer.Option(None, "--cpus", "-c", help="CPU limit (e.g. 2.0). Use 0 for no limit."),
) -> None:
    """Update resource limits.

    Examples:
      raven config resources myapp --memory 8g
      raven config resources myapp --cpus 2.0
      raven config resources myapp --memory 4g --cpus 1.5
    """
    if memory is None and cpus is None:
        console.print("[yellow]No changes specified. Use --memory and/or --cpus.[/yellow]")
        raise typer.Exit(1)

    cfg, path = _load(name)
    changed: list[str] = []

    if memory is not None:
        cfg.resources.memory = memory
        changed.append(f"memory = {memory}")

    if cpus is not None:
        cfg.resources.cpus = cpus
        changed.append(f"cpus = {cpus}")

    save_config(cfg, path)
    _regenerate_unit(name, cfg)
    for c in changed:
        console.print(f"  [cyan]{c}[/cyan]")
    console.print(f"[green]Updated resources for '{name}'.[/green]")
