"""raven setup — run environment setup commands under a guard."""

from __future__ import annotations

import logging
from typing import Optional

import typer

from raven.backends import get_backend
from raven.config.loader import load_config
from raven.state.models import EnvStatus
from raven.state.store import load_state
from raven.util.console import console
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)

def setup(
    name: str = typer.Argument(..., help="Environment name."),
    guard: str = typer.Option("registries", "--guard", "-g", help="Guard to use for setup."),
) -> None:
    """Run the environment setup_commands under a specific guard."""
    config_path = env_dir(name) / "config.yaml"
    try:
        config = load_config(config_path)
    except Exception as e:
        console.print(f"[red]Error loading config:[/red] {e}")
        raise typer.Exit(1)

    if not config.setup_commands:
        console.print("[yellow]No setup_commands defined in config.[/yellow]")
        raise typer.Exit(0)

    backend = get_backend(config)

    if backend.status(name) != EnvStatus.RUNNING:
        console.print(f"[yellow]Environment '{name}' is not running. Starting...[/yellow]")
        backend.start(name)

    state = load_state(name)
    original_guard = state.guard_preset

    console.print(f"[bold]Running setup commands under guard: [cyan]{guard}[/cyan][/bold]")
    
    # Apply temporary guard
    if guard != original_guard:
        try:
            backend.apply_guard(name, guard)
        except Exception as e:
            console.print(f"[red]Error applying guard:[/red] {e}")
            raise typer.Exit(1)

    try:
        for cmd in config.setup_commands:
            console.print(f"[dim]$ {cmd}[/dim]")
            exit_code = backend.exec(name, ["bash", "-c", cmd])
            if exit_code != 0:
                console.print(f"[red]Command failed with exit code {exit_code}:[/red] {cmd}")
                raise typer.Exit(exit_code)
    finally:
        # Restore original guard
        if guard != original_guard:
            console.print(f"[dim]Restoring original guard: {original_guard}...[/dim]")
            try:
                backend.apply_guard(name, original_guard)
            except Exception as e:
                console.print(f"[red]Error restoring guard:[/red] {e}")

    console.print("[bold green]Setup completed successfully.[/bold green]")
