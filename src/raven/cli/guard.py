"""raven guard — control network policy for running environments."""

from __future__ import annotations

import logging
import typer
from rich.table import Table

from raven.backends import get_backend
from raven.config.loader import load_config, save_config
from raven.network.guard import BUILTIN_PRESETS, resolve_preset, show_guard_status
from raven.state.models import EnvStatus
from raven.state.store import load_state
from raven.util.console import console
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)

def guard_cmd(
    name: str = typer.Argument(..., help="Environment name."),
    preset: str = typer.Argument(..., help="Guard preset (open, registries, offline, restricted, or custom)."),
) -> None:
    """Switch the network guard preset and apply it immediately."""
    try:
        state = load_state(name)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Environment '{name}' not found.")
        raise typer.Exit(1)

    config_path = env_dir(name) / "config.yaml"
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error loading config:[/red] {exc}")
        raise typer.Exit(1)

    backend = get_backend(config)
    is_running = backend.status(name) == EnvStatus.RUNNING

    if is_running:
        try:
            backend.apply_guard(name, preset)
        except Exception as exc:
            console.print(f"[red]Error applying guard:[/red] {exc}")
            raise typer.Exit(1)
    
    # Persistent update
    config.network.policy = preset
    save_config(config, config_path)

    status_msg = f"[green]Guard switched to '[cyan]{preset}[/cyan]' for '{name}'.[/green]"
    if not is_running:
        status_msg += " [dim](Environment is not running; will apply on next start).[/dim]"
    
    console.print(status_msg)


def allow(
    name: str = typer.Argument(..., help="Environment name."),
    host: str = typer.Argument(..., help="Hostname to allow (e.g. apt.example.com)."),
) -> None:
    """Add a host to the allowlist and switch to 'restricted' guard."""
    try:
        state = load_state(name)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Environment '{name}' not found.")
        raise typer.Exit(1)

    config_path = env_dir(name) / "config.yaml"
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error loading config:[/red] {exc}")
        raise typer.Exit(1)

    if host in config.network.allowed_hosts:
        console.print(f"[yellow]Host '{host}' is already in the allowlist.[/yellow]")
    else:
        config.network.allowed_hosts.append(host)
    
    # Switch to restricted if not already on a restrictive policy
    if config.network.policy in ("open", "offline"):
        config.network.policy = "restricted"

    save_config(config, config_path)

    backend = get_backend(config)
    if backend.status(name) == EnvStatus.RUNNING:
        try:
            backend.apply_guard(name, config.network.policy)
            console.print(f"[green]Host '{host}' added and rules updated.[/green]")
        except Exception as exc:
            console.print(f"[red]Error applying guard:[/red] {exc}")
            raise typer.Exit(1)
    else:
        console.print(f"[green]Host '{host}' added to allowlist.[/green] [dim](Will apply on next start).[/dim]")
