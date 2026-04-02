"""raven code — launch VS Code connected to an environment."""

from __future__ import annotations

import logging

import typer

from raven.backends import get_backend
from raven.config.loader import load_config
from raven.state.models import EnvStatus
from raven.state.store import load_state
from raven.util.console import console
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)


def code(
    name: str = typer.Argument(help="Environment name."),
    workspace: str = typer.Option("/workspace", "--workspace", "-w", help="Remote workspace path."),
) -> None:
    """Open VS Code connected to an environment via SSH."""
    state = load_state(name)
    config = load_config(env_dir(name) / "config.yaml")
    backend = get_backend(config)

    if state.status != EnvStatus.RUNNING:
        console.print(f"[yellow]Environment '{name}' is not running. Starting...[/yellow]")
        backend.start(name)

    console.print(f"[bold]Setting up VS Code SSH access for '{name}'...[/bold]")
    details = backend.setup_vscode(name, config.vscode)

    console.print(f"[dim]SSH host: {details['host']} (port {details['port']})[/dim]")

    backend.launch_vscode(name, workspace)
