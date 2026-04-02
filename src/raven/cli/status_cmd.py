"""raven status — rich per-environment or global status view."""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from raven.backends import get_backend
from raven.config.loader import load_config
from raven.state.models import EnvStatus
from raven.state.store import list_env_names, load_state
from raven.util.console import console
from raven.util.xdg import env_dir
from raven.cli.list_cmd import STATUS_STYLES, _format_uptime

log = logging.getLogger(__name__)


def _podman_stats(container_name: str) -> tuple[str, str]:
    """Return (cpu%, memory) from podman stats, or ("", "") on failure."""
    try:
        result = subprocess.run(
            ["podman", "stats", "--no-stream", "--format", "json", container_name],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return "", ""
        data = json.loads(result.stdout)
        if isinstance(data, list) and data:
            entry = data[0]
            cpu = entry.get("CPU", entry.get("CPUPerc", ""))
            mem = entry.get("MemUsage", entry.get("Memory", ""))
            return str(cpu), str(mem)
    except Exception as e:
        log.debug("podman stats failed for %s: %s", container_name, e)
    return "", ""


def _status_single(name: str) -> None:
    """Show a detailed status panel for one environment."""
    try:
        state = load_state(name)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Environment '{name}' not found.")
        raise typer.Exit(1)

    try:
        config = load_config(env_dir(name) / "config.yaml")
        backend = get_backend(config)
        live_status = backend.status(name)
        if live_status != state.status:
            state.status = live_status
    except Exception as e:
        log.debug("Could not refresh status for '%s': %s", name, e)
        config = None

    style = STATUS_STYLES.get(state.status, "")
    uptime = _format_uptime(state.started_at) if state.status == EnvStatus.RUNNING else "-"

    cpu, mem = "", ""
    if state.status == EnvStatus.RUNNING:
        cpu, mem = _podman_stats(f"raven-{name}")

    rows = [
        ("Status", f"[{style}]{state.status.value}[/{style}]"),
        ("Backend", state.backend),
        ("Network Policy", state.network_phase.value),
        ("SSH Port", str(state.ssh_port) if state.ssh_port else "-"),
        ("Uptime", uptime),
        ("CPU", cpu or "-"),
        ("Memory", mem or "-"),
        ("Created", state.created_at[:19] if state.created_at else "-"),
    ]
    if config:
        rows.insert(2, ("Image", config.image))
        rows.insert(3, ("Source", str(getattr(config.source, "path", getattr(config.source, "url", "")))))

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="dim", min_width=16)
    table.add_column("Value")
    for k, v in rows:
        table.add_row(k, v)

    console.print(Panel(table, title=f"[bold]{name}[/bold]", border_style=style or "white"))


def _status_all(refresh: bool) -> None:
    """Show a global status table for all environments."""
    names = list_env_names()
    if not names:
        console.print("[dim]No environments found.[/dim]")
        return

    table = Table(title="Raven Environments")
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Uptime")
    table.add_column("Network Policy", style="dim")
    table.add_column("CPU", style="dim")
    table.add_column("Memory", style="dim")
    table.add_column("SSH Port", style="dim")

    for name in names:
        try:
            state = load_state(name)
            if refresh:
                try:
                    config = load_config(env_dir(name) / "config.yaml")
                    live = get_backend(config).status(name)
                    if live != state.status:
                        state.status = live
                except Exception:
                    pass

            style = STATUS_STYLES.get(state.status, "")
            uptime = _format_uptime(state.started_at) if state.status == EnvStatus.RUNNING else "-"
            cpu, mem = ("", "")
            if state.status == EnvStatus.RUNNING:
                cpu, mem = _podman_stats(f"raven-{name}")

            table.add_row(
                state.name,
                f"[{style}]{state.status.value}[/{style}]",
                uptime,
                state.network_phase.value,
                cpu or "-",
                mem or "-",
                str(state.ssh_port) if state.ssh_port else "-",
            )
        except Exception as e:
            table.add_row(name, f"[red]error: {e}[/red]", "", "", "", "", "")

    console.print(table)


def status(
    name: Optional[str] = typer.Argument(None, help="Environment name. If omitted, shows all environments."),
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Refresh live status from backend."),
) -> None:
    """Show environment status. Detailed view for one env, table for all."""
    if name:
        _status_single(name)
    else:
        _status_all(refresh)
