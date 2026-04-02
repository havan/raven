"""raven create — create a new isolated development environment."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel

from raven.backends import get_backend
from raven.config.loader import load_config, save_config
from raven.util.console import console
from raven.util.xdg import ensure_dirs

log = logging.getLogger(__name__)


def create(
    name: Optional[str] = typer.Argument(None, help="Environment name (overrides name in config)."),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to raven.yaml config file."),
    start_after: bool = typer.Option(False, "--start", "-s", help="Start the environment after creating it."),
) -> None:
    """Create a new isolated development environment from a YAML config."""
    ensure_dirs()

    cfg = load_config(config)
    if name:
        cfg.name = name

    backend = get_backend(cfg)

    try:
        container_id = backend.create(cfg)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Save canonical config copy
    save_config(cfg)

    console.print(Panel(
        f"[bold green]Environment created:[/bold green] {cfg.name}\n"
        f"[dim]Backend:[/dim] {cfg.backend.value}\n"
        f"[dim]Image:[/dim] {cfg.image}\n"
        f"[dim]Container:[/dim] {container_id}",
        title="raven create",
        border_style="green",
    ))

    if start_after:
        try:
            backend.start(cfg.name)
            console.print(f"[green]Environment '{cfg.name}' started.[/green]")
        except RuntimeError as e:
            console.print(f"[yellow]Environment created but failed to start:[/yellow] {e}")
            raise typer.Exit(1)
