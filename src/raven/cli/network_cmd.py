"""raven network — inspect and control network policy for running environments."""

from __future__ import annotations

import logging

import typer
from rich.table import Table

from raven.backends import get_backend
from raven.config.loader import load_config, save_config
from raven.network.allowlists import load_resolved_ips
from raven.state.models import EnvStatus, NetworkPhase
from raven.state.store import load_state
from raven.util.console import console
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)

_LEGACY_POLICY_MAP: dict[str, str] = {"allowlist": "restricted", "block": "offline"}
_VALID_POLICIES = ("open", "restricted", "offline")

network_app = typer.Typer(
    name="network",
    help="Inspect and control the network policy of an environment.",
    no_args_is_help=True,
)


@network_app.command(name="status")
def status(
    name: str = typer.Argument(..., help="Environment name."),
) -> None:
    """Show the current network policy, allowed hosts, and active CIDRs."""
    try:
        state = load_state(name)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Environment '{name}' not found.")
        raise typer.Exit(1)

    try:
        config = load_config(env_dir(name) / "config.yaml")
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error loading config:[/red] {exc}")
        raise typer.Exit(1)

    cidrs = load_resolved_ips(name)
    run_cfg = config.network.run_phase
    install_cfg = config.network.install_phase

    # Header line
    status_color = "green" if state.status == EnvStatus.RUNNING else "yellow"
    console.print(
        f"[bold]Environment:[/bold] {name}   "
        f"[bold]Status:[/bold] [{status_color}]{state.status.value}[/{status_color}]"
    )

    t = Table(show_header=False, box=None, padding=(0, 1))
    t.add_column(style="dim", no_wrap=True)
    t.add_column()

    t.add_row("Phase:", state.network_phase.value)
    t.add_row("Run policy:", f"[cyan]{run_cfg.policy}[/cyan]")

    if run_cfg.allowed_hosts:
        t.add_row("Run allowed hosts:", ", ".join(run_cfg.allowed_hosts))
    else:
        t.add_row("Run allowed hosts:", "[dim](none)[/dim]")

    t.add_row("Install allowed hosts:", ", ".join(install_cfg.allowed_hosts) or "[dim](none)[/dim]")

    if cidrs:
        cidr_note = "" if state.status == EnvStatus.RUNNING else " [dim](from last session)[/dim]"
        t.add_row("Active CIDRs:", ", ".join(cidrs) + cidr_note)
    else:
        t.add_row("Active CIDRs:", "[dim](not yet resolved — run raven install or raven network policy)[/dim]")

    console.print(t)


@network_app.command(name="policy")
def policy_cmd(
    name: str = typer.Argument(..., help="Environment name."),
    new_policy: str = typer.Argument(..., help="Policy: open, restricted, or offline."),
) -> None:
    """Switch the run-phase network policy and apply it immediately."""
    normalized = _LEGACY_POLICY_MAP.get(new_policy, new_policy)
    if normalized not in _VALID_POLICIES:
        console.print(
            f"[red]Error:[/red] Invalid policy '{new_policy}'. "
            f"Valid options: {', '.join(_VALID_POLICIES)}"
        )
        raise typer.Exit(1)

    try:
        state = load_state(name)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Environment '{name}' not found.")
        raise typer.Exit(1)

    config_path = env_dir(name) / "config.yaml"
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error loading config:[/red] {exc}")
        raise typer.Exit(1)

    if config.network.run_phase.policy == normalized:
        console.print(f"Policy is already '[cyan]{normalized}[/cyan]'. No change.")
        raise typer.Exit(0)

    if state.network_phase == NetworkPhase.INSTALL:
        config.network.run_phase.policy = normalized  # type: ignore[assignment]
        save_config(config, config_path)
        console.print(
            f"[green]Policy updated to '{normalized}'.[/green] "
            "[dim]Environment is in install phase; rule will apply when switching to run phase.[/dim]"
        )
        raise typer.Exit(0)

    if state.status != EnvStatus.RUNNING:
        console.print(
            f"[red]Error:[/red] Environment '{name}' is not running. "
            "Use [cyan]raven edit[/cyan] to change config for next start."
        )
        raise typer.Exit(1)

    if normalized == "restricted" and not config.network.run_phase.allowed_hosts:
        console.print(
            "[yellow]Warning:[/yellow] No allowed_hosts configured. "
            "Switching to 'restricted' will block all traffic. "
            "Use [cyan]raven allow[/cyan] to add hosts first."
        )
        typer.confirm("Switch to restricted anyway?", abort=True)

    config.network.run_phase.policy = normalized  # type: ignore[assignment]
    save_config(config, config_path)

    backend = get_backend(config)
    try:
        backend.apply_network_phase(name, NetworkPhase.RUN)
    except Exception as exc:
        console.print(f"[red]Error applying network rules:[/red] {exc}")
        raise typer.Exit(1)

    console.print(f"[green]Network policy switched to '[cyan]{normalized}[/cyan]' for '{name}'.[/green]")


def allow(
    name: str = typer.Argument(..., help="Environment name."),
    host: str = typer.Argument(..., help="Hostname to allow (e.g. apt.example.com)."),
) -> None:
    """Add a host to the run-phase allowlist and apply rules immediately."""
    try:
        state = load_state(name)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Environment '{name}' not found.")
        raise typer.Exit(1)

    config_path = env_dir(name) / "config.yaml"
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Error loading config:[/red] {exc}")
        raise typer.Exit(1)

    if host in config.network.run_phase.allowed_hosts:
        console.print(f"[yellow]Host '{host}' is already in the allowlist.[/yellow]")
        raise typer.Exit(0)

    config.network.run_phase.allowed_hosts.append(host)

    if state.status != EnvStatus.RUNNING:
        save_config(config, config_path)
        console.print(
            f"[green]Host '{host}' saved to allowlist.[/green] "
            "[dim]Environment is not running; rules will apply on next start.[/dim]"
        )
        raise typer.Exit(0)

    if state.network_phase == NetworkPhase.INSTALL:
        save_config(config, config_path)
        console.print(
            f"[green]Host '{host}' saved to allowlist.[/green] "
            "[dim]Currently in install phase; rules will apply when switching to run phase.[/dim]"
        )
        raise typer.Exit(0)

    # If policy is open or offline, switch to restricted
    current_policy = config.network.run_phase.policy
    if current_policy in ("open", "offline"):
        config.network.run_phase.policy = "restricted"  # type: ignore[assignment]

    save_config(config, config_path)

    backend = get_backend(config)
    try:
        backend.apply_network_phase(name, NetworkPhase.RUN)
    except Exception as exc:
        console.print(f"[red]Error applying network rules:[/red] {exc}")
        raise typer.Exit(1)

    cidrs = load_resolved_ips(name)
    cidr_count = len(cidrs)
    policy_note = ""
    if current_policy in ("open", "offline"):
        policy_note = f" [dim](policy switched from '{current_policy}' to 'restricted')[/dim]"
    console.print(
        f"[green]Host '{host}' added and rules updated "
        f"({cidr_count} CIDRs active).{policy_note}[/green]"
    )
