"""raven ps — show running processes and resource usage."""

from __future__ import annotations

import logging

import typer
from rich.table import Table

from raven.backends.podman.systemd import container_name
from raven.config.loader import load_config
from raven.config.schema import BackendType
from raven.state.models import EnvStatus
from raven.state.store import load_state
from raven.util.console import console
from raven.util.subprocess import run
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)


def ps(
    name: str = typer.Argument(help="Environment name."),
) -> None:
    """Show processes, ports, and resource usage for an environment."""
    config = load_config(env_dir(name) / "config.yaml")
    if config.backend != BackendType.PODMAN:
        console.print("[red]Error:[/red] 'raven ps' only supports Podman environments.")
        raise typer.Exit(1)

    state = load_state(name)

    if state.status != EnvStatus.RUNNING:
        console.print(f"[yellow]Environment '{name}' is not running.[/yellow]")
        raise typer.Exit(1)

    cname = container_name(name)

    # Resource usage
    stats = run(
        ["podman", "stats", "--no-stream", "--format",
         "{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}",
         cname],
        check=False,
    )
    if stats.returncode == 0 and stats.stdout.strip():
        parts = stats.stdout.strip().split("\t")
        info_table = Table(title=f"Resources: {name}", show_header=False)
        info_table.add_column("Metric", style="bold")
        info_table.add_column("Value")
        labels = ["CPU", "Memory", "Network I/O", "Block I/O"]
        for label, value in zip(labels, parts):
            info_table.add_row(label, value.strip())
        console.print(info_table)

    # Port bindings
    ports_result = run(
        ["podman", "port", cname],
        check=False,
    )
    if ports_result.returncode == 0 and ports_result.stdout.strip():
        console.print("\n[bold]Ports:[/bold]")
        console.print(ports_result.stdout.strip())

    # Processes inside the container
    procs = run(
        ["podman", "exec", cname, "ps", "aux", "--no-headers"],
        check=False,
    )
    if procs.returncode == 0 and procs.stdout.strip():
        proc_table = Table(title=f"Processes: {name}")
        proc_table.add_column("USER", style="dim")
        proc_table.add_column("PID")
        proc_table.add_column("CPU%")
        proc_table.add_column("MEM%")
        proc_table.add_column("COMMAND", max_width=60)
        for line in procs.stdout.strip().split("\n"):
            cols = line.split(None, 10)
            if len(cols) >= 11:
                proc_table.add_row(cols[0], cols[1], cols[2], cols[3], cols[10])
        console.print(proc_table)
