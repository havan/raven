"""raven list — list all environments."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional
import typer
from rich.table import Table
from raven.backends import get_backend
from raven.config.loader import load_config
from raven.state.models import EnvStatus
from raven.state.store import list_env_names, load_state, save_state
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


def _live_status(name: str) -> EnvStatus:
    try:
        config = load_config(env_dir(name) / "config.yaml")
        return get_backend(config).status(name)
    except Exception as e:
        log.debug("Live status check failed for '%s': %s", name, e)
        return EnvStatus.UNKNOWN


def _format_uptime(started_at_str: str | None) -> str:
    if not started_at_str:
        return "-"
    try:
        started_at = datetime.fromisoformat(started_at_str)
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
        log.warning("Could not parse started_at timestamp: %s", started_at_str)
        return "?"


def list_envs(
    refresh: bool = False,
    stats: bool = False,
) -> None:
    """Core logic to list all raven-managed environments."""
    names = list_env_names()
    if not names:
        console.print("[dim]No environments found.[/dim]")
        return

    table = Table(title="Raven Environments")
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Uptime")
    if stats:
        table.add_column("CPU")
        table.add_column("Memory")
    table.add_column("Backend", style="dim")
    table.add_column("SSH Port", style="dim")
    table.add_column("Network", style="dim")
    table.add_column("Created", style="dim")

    for name in names:
        try:
            state = load_state(name)
            if refresh:
                live = _live_status(name)
                if live != state.status:
                    state.status = live
                    if live != EnvStatus.UNKNOWN:
                        save_state(state)

            style = STATUS_STYLES.get(state.status, "")
            uptime = (
                _format_uptime(state.started_at)
                if state.status == EnvStatus.RUNNING
                else "-"
            )

            row = [
                state.name,
                f"[{style}]{state.status.value}[/{style}]",
                uptime,
            ]
            
            if stats:
                if state.status == EnvStatus.RUNNING:
                    try:
                        config = load_config(env_dir(name) / "config.yaml")
                        backend = get_backend(config)
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
                state.backend,
                str(state.ssh_port) if state.ssh_port else "-",
                state.network_phase.value,
                state.created_at[:19] if state.created_at else "-",
            ])
            table.add_row(*row)
        except Exception as e:
            table.add_row(name, f"[red]error: {e}[/red]", "", *([ "" ] * (6 if stats else 4)))

    console.print(table)


def list_cmd(
    refresh: bool = typer.Option(
        False, "--refresh", "-r", help="Refresh live status from backend."
    ),
    stats: bool = typer.Option(
        False, "--stats", "-s", help="Show live CPU and memory usage (slower)."
    ),
) -> None:
    """List all raven-managed environments."""
    list_envs(refresh=refresh, stats=stats)


def ps(
    name: Optional[str] = typer.Argument(None, help="Environment name. If provided, shows processes inside."),
    refresh: bool = typer.Option(False, "--refresh", "-r", help="Refresh live status from backend (if listing)."),
    stats: bool = typer.Option(False, "--stats", "-s", help="Show live CPU and memory usage (if listing)."),
) -> None:
    """List environments or show processes for one."""
    if name:
        from raven.cli.top_cmd import top as top_cmd
        top_cmd(name)
    else:
        list_envs(refresh=refresh, stats=stats)

