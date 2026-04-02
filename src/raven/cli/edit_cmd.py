"""raven edit — open the configuration file in an editor."""

from __future__ import annotations

import os
import shlex
import shutil
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
        editor_cmd = shlex.split(editor)
        if not editor_cmd or not shutil.which(editor_cmd[0]):
            editor_cmd = ["nano"]
    except ValueError:
        editor_cmd = ["nano"]

    try:
        subprocess.run([*editor_cmd, str(config_path)], check=True)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Could not find editor '{editor}'. Please set $EDITOR.")
        raise typer.Exit(1)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] Editor '{editor}' failed with exit code {e.returncode}.")
        raise typer.Exit(1)
