"""raven start/stop/shell/destroy/restart/purge commands."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from raven.backends import get_backend
from raven.config.loader import load_config
from raven.config.schema import EnvConfig
from raven.state.models import EnvStatus
from raven.state.store import load_state
from raven.util.console import console
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)


def _load_env_config(name: str) -> EnvConfig:
    """Load the canonical config for an environment."""
    config_path = env_dir(name) / "config.yaml"
    return load_config(config_path)


def _get_backend_for_env(name: str):
    config = _load_env_config(name)
    return get_backend(config), config


def start(
    name: str = typer.Argument(..., help="Environment name."),
) -> None:
    """Start an environment."""
    backend, _ = _get_backend_for_env(name)
    backend.start(name)
    console.print(f"[green]Environment '{name}' started.[/green]")


def stop(
    name: str = typer.Argument(..., help="Environment name."),
) -> None:
    """Stop a running environment."""
    backend, _ = _get_backend_for_env(name)
    backend.stop(name)
    console.print(f"[yellow]Environment '{name}' stopped.[/yellow]")


def shell(
    name: str = typer.Argument(..., help="Environment name."),
    shell_bin: str = typer.Option("/bin/bash", "--shell", "-s", help="Shell binary to use."),
) -> None:
    """Open an interactive shell inside an environment."""
    backend, _ = _get_backend_for_env(name)
    if backend.status(name) != EnvStatus.RUNNING:
        console.print(f"[yellow]Environment '{name}' is not running. Starting...[/yellow]")
        backend.start(name)
    backend.shell(name, shell_binary=shell_bin)


def destroy(
    name: str = typer.Argument(..., help="Environment name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Destroy an environment (stop + remove all resources)."""
    from raven.state.store import delete_state, state_exists

    e_dir = env_dir(name)
    if not e_dir.exists() and not state_exists(name):
        console.print(f"[red]Error:[/red] Environment '{name}' does not exist.")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"Destroy environment '{name}'? This cannot be undone")
        if not confirm:
            raise typer.Exit()

    # Try to read the workspace path now, before we delete anything
    workspace: Path | None = None
    config = None
    try:
        config = _load_env_config(name)
        from raven.config.schema import SourceMount
        if isinstance(config.source, SourceMount):
            workspace = Path(config.source.path)
    except Exception as exc:
        log.warning("Could not load config for '%s': %s", name, exc)

    # Get backend
    backend = None
    try:
        if config is not None:
            backend = get_backend(config)
        elif state_exists(name):
            state = load_state(name)
            backend = get_backend(state.backend)
        else:
            backend = get_backend("podman")
    except Exception as exc:
        log.warning("Could not instantiate backend for '%s': %s", name, exc)

    if backend is not None:
        try:
            backend.destroy(name)
            delete_state(name)
            if e_dir.exists():
                import shutil
                shutil.rmtree(e_dir, ignore_errors=True)
            console.print(f"[red]Environment '{name}' destroyed.[/red]")
        except Exception as exc:
            log.warning("Backend destroy failed for '%s': %s", name, exc)
            console.print(f"[yellow]Warning:[/yellow] Backend cleanup failed: {exc}")
            raise typer.Exit(1)

    if workspace is not None and workspace.exists():
        console.print(f"[yellow]Note:[/yellow] Workspace was not removed: {workspace}")


def restart(
    name: str = typer.Argument(..., help="Environment name."),
) -> None:
    """Restart an environment (stop then start)."""
    backend, _ = _get_backend_for_env(name)
    if backend.status(name) == EnvStatus.RUNNING:
        backend.stop(name)
    backend.start(name)
    console.print(f"[green]Environment '{name}' restarted.[/green]")


def purge(
    name: str = typer.Argument(..., help="Environment name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Remove dependency directories (node_modules, .venv, etc.) defined in config."""
    backend, config = _get_backend_for_env(name)
    
    purge_dirs = config.purge.purge_dirs
    mount_path = config.source.mount_path
    
    if not purge_dirs:
        console.print("[yellow]No purge_dirs defined in config.[/yellow]")
        raise typer.Exit(0)

    if not yes:
        dirs_str = ", ".join(purge_dirs)
        confirm = typer.confirm(f"Purge directories [{dirs_str}] under {mount_path}?")
        if not confirm:
            raise typer.Exit()

    if backend.status(name) != EnvStatus.RUNNING:
        console.print(f"[yellow]Environment '{name}' is not running. Starting to perform purge...[/yellow]")
        backend.start(name)

    for d in purge_dirs:
        full_path = f"{mount_path}/{d}"
        console.print(f"[dim]Purging {full_path}...[/dim]")
        backend.exec(name, ["rm", "-rf", full_path])
    
    console.print("[green]Purge completed.[/green]")
