"""raven top — show running processes and resource usage inside an environment."""

from __future__ import annotations

import logging

import typer
from rich.table import Table

from raven.backends import get_backend
from raven.config.loader import load_config
from raven.state.models import EnvStatus
from raven.util.console import console
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)


def top(
    name: str = typer.Argument(help="Environment name."),
) -> None:
    """Show processes, ports, and resource usage for an environment."""
    config = load_config(env_dir(name) / "config.yaml")
    backend = get_backend(config)

    if backend.status(name) != EnvStatus.RUNNING:
        console.print(f"[yellow]Environment '{name}' is not running.[/yellow]")
        raise typer.Exit(1)

    try:
        data = backend.get_processes(name)
    except NotImplementedError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Resource usage
    resources = data.get("resources", {})
    if resources:
        info_table = Table(title=f"Resources: {name}", show_header=False)
        info_table.add_column("Metric", style="bold")
        info_table.add_column("Value")
        info_table.add_row("CPU", resources.get("cpu", "N/A"))
        info_table.add_row("Memory", resources.get("memory", "N/A"))
        info_table.add_row("Network I/O", resources.get("net_io", "N/A"))
        info_table.add_row("Block I/O", resources.get("block_io", "N/A"))
        console.print(info_table)

    # Processes inside the container
    processes = data.get("processes", [])
    if processes:
        proc_table = Table(title=f"Processes: {name}")
        proc_table.add_column("USER", style="dim")
        proc_table.add_column("PID")
        proc_table.add_column("CPU%")
        proc_table.add_column("MEM%")
        proc_table.add_column("COMMAND", max_width=60)
        for p in processes:
            proc_table.add_row(
                p.get("user", ""),
                p.get("pid", ""),
                p.get("cpu", ""),
                p.get("mem", ""),
                p.get("command", ""),
            )
        console.print(proc_table)
