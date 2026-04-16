"""raven run — run a command inside an environment."""

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

def run_cmd(
    name: str = typer.Argument(..., help="Environment name."),
    command: list[str] = typer.Argument(..., help="Command to run inside the environment."),
    guard: Optional[str] = typer.Option(None, "--guard", "-g", help="Temporary network guard for this command."),
    workdir: Optional[str] = typer.Option(None, "--workdir", "-w", help="Working directory."),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="User to run as."),
) -> None:
    """Run a command inside an environment, optionally under a specific guard."""
    config_path = env_dir(name) / "config.yaml"
    try:
        config = load_config(config_path)
    except Exception as e:
        console.print(f"[red]Error loading config:[/red] {e}")
        raise typer.Exit(1)

    backend = get_backend(config)

    if backend.status(name) != EnvStatus.RUNNING:
        console.print(f"[yellow]Environment '{name}' is not running. Starting...[/yellow]")
        backend.start(name)

    state = load_state(name)
    original_guard = state.guard_preset
    log.debug("Original guard: %s, target guard: %s", original_guard, guard)

    # Apply temporary guard
    if guard and guard != original_guard:
        console.print(f"[dim]Switching to temporary guard: {guard}...[/dim]")
        try:
            backend.apply_guard(name, guard)
        except Exception as e:
            console.print(f"[red]Error applying guard:[/red] {e}")
            raise typer.Exit(1)

    try:
        exit_code = backend.exec(
            name,
            command,
            workdir=workdir,
            user=user,
            tty=True,
            interactive=True,
        )
    finally:
        # Restore original guard
        if guard and guard != original_guard:
            console.print(f"[dim]Restoring original guard: {original_guard}...[/dim]")
            try:
                backend.apply_guard(name, original_guard)
            except Exception as e:
                console.print(f"[red]Error restoring guard:[/red] {e}")
                # We don't raise here to preserve the exit code of the command

    raise typer.Exit(exit_code)
