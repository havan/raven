"""raven list — list all environments."""

from __future__ import annotations

import logging

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
    """Query podman for the actual container status."""
    try:
        config = load_config(env_dir(name) / "config.yaml")
        return get_backend(config).status(name)
    except Exception:
        return EnvStatus.UNKNOWN


def list_envs() -> None:
    """List all raven-managed environments."""
    names = list_env_names()

    if not names:
        console.print("[dim]No environments found.[/dim]")
        return

    table = Table(title="Raven Environments")
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Backend", style="dim")
    table.add_column("SSH Port", style="dim")
    table.add_column("Network Phase", style="dim")
    table.add_column("Created")

    for name in names:
        try:
            state = load_state(name)
            live = _live_status(name)
            # Reconcile stale state with actual podman status
            if live != EnvStatus.UNKNOWN and live != state.status:
                log.debug(
                    "Reconciling state for '%s': %s → %s",
                    name, state.status.value, live.value,
                )
                state.status = live
                save_state(state)
            style = STATUS_STYLES.get(state.status, "")
            table.add_row(
                state.name,
                f"[{style}]{state.status.value}[/{style}]",
                state.backend,
                str(state.ssh_port) if state.ssh_port else "-",
                state.network_phase.value,
                state.created_at[:19] if state.created_at else "-",
            )
        except Exception as e:
            table.add_row(name, f"[red]error: {e}[/red]", "", "", "", "")

    console.print(table)
