"""raven list — list all environments."""
from __future__ import annotations
import logging
import re
from datetime import datetime, timezone
from typing import Optional
import typer
from rich.table import Table
from raven.backends import get_backend
from raven.config.loader import load_config
from raven.state.models import EnvStatus
from raven.state.store import list_env_names, load_state
from raven.util.console import console
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)

STATUS_STYLES = {
    EnvStatus.RUNNING: "bold green",
    EnvStatus.STOPPED: "yellow",
    EnvStatus.CREATED: "cyan",
    EnvStatus.ERROR: "bold red",
    EnvStatus.UNKNOWN: "dim",
}


def _parse_timestamp(ts: str) -> datetime:
    """Parse a timestamp from podman inspect.

    Podman can return formats like "2026-04-02 14:36:33.939205697 +0300 +03"
    which have nanoseconds (9 digits) and a duplicate trailing timezone name.
    Python's datetime only handles up to microseconds and a single tz offset.
    """
    # Strip duplicate trailing timezone (e.g., " +0300 +03" → " +0300")
    ts = re.sub(r'(\s[+-]\d{4})\s+\S+$', r'\1', ts.strip())
    # Truncate nanoseconds to microseconds
    ts = re.sub(r'(\.\d{6})\d+', r'\1', ts)
    try:
        return datetime.strptime(ts, '%Y-%m-%d %H:%M:%S.%f %z')
    except ValueError:
        return datetime.strptime(ts, '%Y-%m-%d %H:%M:%S %z')


def _format_uptime(started_at_str: str | None) -> str:
    if not started_at_str:
        return "-"
    try:
        started_at = _parse_timestamp(started_at_str)
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        delta = datetime.now(timezone.utc) - started_at
        if delta.total_seconds() < 0:
            return "?"  # Clock skew

        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {minutes}m"
        if minutes > 0:
            return f"{minutes}m"
        return f"{delta.seconds}s"
    except (ValueError, TypeError):
        log.debug("Could not parse started_at timestamp: %s", started_at_str)
        return "?"


def list_envs(
    stats: bool = False,
) -> None:
    """Core logic to list all raven-managed environments."""
    names = list_env_names()
    if not names:
        console.print("[dim]No environments found.[/dim]")
        return

    table = Table(title="Raven Environments")
    table.add_column("Name", style="bold cyan")
    table.add_column("Status")
    table.add_column("Guard")
    table.add_column("Uptime")
    if stats:
        table.add_column("CPU")
        table.add_column("Memory")
    table.add_column("SSH", style="dim")
    table.add_column("Ports", style="dim")

    for name in names:
        try:
            state = load_state(name)
            config = load_config(env_dir(name) / "config.yaml")
            backend = get_backend(config)
            live_status = backend.status(name)

            style = STATUS_STYLES.get(live_status, "")
            uptime = (
                _format_uptime(backend.get_started_at(name))
                if live_status == EnvStatus.RUNNING
                else "-"
            )

            # Format port forwards for the list view
            ports_summary = "-"
            if config.network.port_forwards:
                ports_summary = ", ".join([str(pf.host) for pf in config.network.port_forwards[:3]])
                if len(config.network.port_forwards) > 3:
                    ports_summary += "..."

            row = [
                state.name,
                f"[{style}]{live_status.value}[/{style}]",
                state.guard_preset,
                uptime,
            ]

            if stats:
                if live_status == EnvStatus.RUNNING:
                    try:
                        res = backend.get_stats(name)
                        row.append(res.get("cpu", "-"))
                        row.append(res.get("memory", "-"))
                    except Exception:
                        row.append("-")
                        row.append("-")
                else:
                    row.append("-")
                    row.append("-")

            row.extend([
                str(state.ssh_port) if state.ssh_port else "-",
                ports_summary,
            ])
            table.add_row(*row)
        except Exception as e:
            table.add_row(name, f"[red]error: {e}[/red]", "", *([""] * (6 if stats else 4)))

    console.print(table)


def list_cmd(
    stats: bool = typer.Option(
        False, "--stats", "-s", help="Show live CPU and memory usage (slower)."
    ),
) -> None:
    """List all raven-managed environments."""
    list_envs(stats=stats)


def ps(
    name: Optional[str] = typer.Argument(None, help="Environment name. If provided, shows processes inside."),
    stats: bool = typer.Option(False, "--stats", "-s", help="Show live CPU and memory usage (if listing)."),
) -> None:
    """List environments or show processes for one."""
    if name:
        from raven.cli.top_cmd import top as top_cmd
        top_cmd(name)
    else:
        list_envs(stats=stats)
