"""raven edit — open the configuration file in an editor."""

from __future__ import annotations

import os
import subprocess

import typer

from raven.util.console import console
from raven.util.xdg import env_dir


def edit(name: str = typer.Argument(..., help="Environment name.")) -> None:
    """Edit the configuration file for an environment in the default editor."""
    e_dir = env_dir(name)
    config_path = e_dir / "config.yaml"

    if not config_path.exists():
        console.print(f"[red]Error:[/red] Configuration file not found for environment '{name}'.")
        console.print(f"Looked at: {config_path}")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR", "nano")

    try:
        subprocess.run([editor, str(config_path)])
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Could not find editor '{editor}'. Please set $EDITOR.")
        raise typer.Exit(1)
