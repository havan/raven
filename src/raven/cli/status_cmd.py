"""raven status — rich per-environment or global status view."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from raven.backends import get_backend
from raven.config.loader import load_config
from raven.state.models import EnvStatus
from raven.state.store import load_state
from raven.util.console import console
from raven.util.xdg import env_dir
from raven.cli.list_cmd import STATUS_STYLES, _format_uptime, list_envs

log = logging.getLogger(__name__)


def _status_single(name: str) -> None:
    """Show a detailed status panel for one environment."""
    try:
        state = load_state(name)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Environment '{name}' not found.")
        raise typer.Exit(1)

    live_status = EnvStatus.UNKNOWN
    config = None
    backend = None
    try:
        config = load_config(env_dir(name) / "config.yaml")
        backend = get_backend(config)
        live_status = backend.status(name)
    except Exception as e:
        log.debug("Could not get live status for '%s': %s", name, e)

    style = STATUS_STYLES.get(live_status, "")
    uptime = _format_uptime(backend.get_started_at(name)) if live_status == EnvStatus.RUNNING and backend else "-"

    cpu, mem = "-", "-"
    if live_status == EnvStatus.RUNNING and backend:
        try:
            stats = backend.get_stats(name)
            cpu = stats.get("cpu", "-")
            mem = stats.get("memory", "-")
        except Exception:
            pass

    rows = [
        ("Status", f"[{style}]{live_status.value}[/{style}]"),
        ("Backend", state.backend),
        ("Network Policy", state.network_phase.value),
        ("SSH Port", str(state.ssh_port) if state.ssh_port else "-"),
        ("Uptime", uptime),
        ("CPU", cpu),
        ("Memory", mem),
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


def status(
    name: Optional[str] = typer.Argument(None, help="Environment name. If omitted, shows all environments."),
    stats: bool = typer.Option(False, "--stats", "-s", help="Show live CPU and memory usage (slower)."),
) -> None:
    """Show environment status. Detailed view for one env, table for all."""
    if name:
        _status_single(name)
    else:
        list_envs(stats=stats)
