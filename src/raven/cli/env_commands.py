"""raven start/stop/shell/destroy/install/reinstall/run commands."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from raven.backends import get_backend
from raven.config.loader import load_config
from raven.config.schema import EnvConfig
from raven.state.models import EnvStatus, NetworkPhase
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
    name: str = typer.Argument(help="Environment name."),
) -> None:
    """Start an environment."""
    backend, _ = _get_backend_for_env(name)
    backend.start(name)
    console.print(f"[green]Environment '{name}' started.[/green]")


def stop(
    name: str = typer.Argument(help="Environment name."),
) -> None:
    """Stop a running environment."""
    backend, _ = _get_backend_for_env(name)
    backend.stop(name)
    console.print(f"[yellow]Environment '{name}' stopped.[/yellow]")


def shell(
    name: str = typer.Argument(help="Environment name."),
    shell_bin: str = typer.Option("/bin/bash", "--shell", "-s", help="Shell binary to use."),
) -> None:
    """Open an interactive shell inside an environment."""
    backend, _ = _get_backend_for_env(name)
    state = load_state(name)
    if state.status != EnvStatus.RUNNING:
        console.print(f"[yellow]Environment '{name}' is not running. Starting...[/yellow]")
        backend.start(name)
    backend.shell(name, shell_binary=shell_bin)


def destroy(
    name: str = typer.Argument(help="Environment name."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Destroy an environment (stop + remove all resources)."""
    from raven.config.schema import SourceMount
    from raven.state.store import delete_state, state_exists
    from raven.util.xdg import env_dir

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
        if isinstance(config.source, SourceMount):
            workspace = Path(config.source.path)
    except Exception as exc:
        log.warning("Could not load config for '%s': %s", name, exc)
        console.print(f"[yellow]Warning:[/yellow] Could not load config: {exc}")

    # Get backend — try from config first, fall back to Podman (name is enough for cleanup)
    backend = None
    try:
        if config is not None:
            backend = get_backend(config)
        else:
            from raven.backends.podman.backend import PodmanBackend
            backend = PodmanBackend()
    except Exception as exc:
        log.warning("Could not instantiate backend for '%s': %s", name, exc)
        console.print(f"[yellow]Warning:[/yellow] Could not load backend: {exc}")

    # Run backend cleanup
    if backend is not None:
        try:
            backend.destroy(name)
            console.print(f"[red]Environment '{name}' destroyed.[/red]")
        except Exception as exc:
            log.warning("Backend destroy failed for '%s': %s", name, exc)
            console.print(f"[yellow]Warning:[/yellow] Backend cleanup failed: {exc}")
            console.print(
                f"[dim]The environment state was NOT removed. You may need to manually clean up resources\n"
                f"and then run 'raven destroy {name}' again.[/dim]"
            )
            raise typer.Exit(1)

    if workspace is not None and workspace.exists():
        console.print(
            f"[yellow]Note:[/yellow] Workspace was not removed — it lives outside raven's control:\n"
            f"  {workspace}"
        )


def install(
    name: str = typer.Argument(help="Environment name."),
) -> None:
    """Run setup commands with restricted network (install phase).

    Only approved package registries are reachable during this phase.
    """
    backend, config = _get_backend_for_env(name)
    state = load_state(name)

    if state.status != EnvStatus.RUNNING:
        console.print(f"[yellow]Environment '{name}' is not running. Starting...[/yellow]")
        backend.start(name)

    if not config.setup_commands:
        console.print("[yellow]No setup_commands defined in config.[/yellow]")
        raise typer.Exit()

    console.print("[bold]Switching to install phase (restricted network)...[/bold]")
    try:
        backend.apply_network_phase(name, NetworkPhase.INSTALL)
    except Exception as e:
        log.warning("Could not apply network rules: %s", e)
        console.print(f"[yellow]Warning: Network isolation not applied: {e}[/yellow]")

    failed = False
    for cmd in config.setup_commands:
        console.print(f"[dim]$ {cmd}[/dim]")
        exit_code = backend.exec(name, ["bash", "-c", cmd])
        if exit_code != 0:
            console.print(f"[red]Command failed with exit code {exit_code}:[/red] {cmd}")
            failed = True
            break

    if failed:
        console.print("[red]Install phase failed. Network remains restricted.[/red]")
        raise typer.Exit(1)

    console.print("[bold]Switching to run phase...[/bold]")
    try:
        backend.apply_network_phase(name, NetworkPhase.RUN)
    except Exception as e:
        log.warning("Could not restore network rules: %s", e)

    console.print("[green]Install completed successfully.[/green]")


def reinstall(
    name: str = typer.Argument(help="Environment name."),
    cmd: Optional[list[str]] = typer.Option(None, "--cmd", help="Command(s) to run instead of config defaults."),
    purge: bool = typer.Option(False, "--purge", help="Remove dependency directories before reinstalling."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts."),
) -> None:
    """Reinstall dependencies with restricted network.

    Temporarily switches to install-phase network policy, runs install commands,
    then restores the previous network phase.
    """
    backend, config = _get_backend_for_env(name)
    state = load_state(name)

    if state.status != EnvStatus.RUNNING:
        console.print(f"[yellow]Environment '{name}' is not running. Starting...[/yellow]")
        backend.start(name)

    # Determine which commands to run
    commands = cmd or config.reinstall.commands or config.setup_commands
    if not commands:
        console.print("[yellow]No commands to run.[/yellow]")
        raise typer.Exit()

    # Purge dependency directories
    if purge:
        purge_dirs = config.reinstall.purge_dirs
        mount_path = config.source.mount_path
        if not yes:
            dirs_str = ", ".join(purge_dirs)
            confirm = typer.confirm(
                f"Purge directories [{dirs_str}] under {mount_path}?"
            )
            if not confirm:
                raise typer.Exit()

        for d in purge_dirs:
            full_path = f"{mount_path}/{d}"
            console.print(f"[dim]Purging {full_path}...[/dim]")
            backend.exec(name, ["rm", "-rf", full_path])

    # Save current phase to restore later
    previous_phase = state.network_phase

    console.print("[bold]Switching to install phase (restricted network)...[/bold]")
    try:
        backend.apply_network_phase(name, NetworkPhase.INSTALL)
    except Exception as e:
        log.warning("Could not apply network rules: %s", e)
        console.print(f"[yellow]Warning: Network isolation not applied: {e}[/yellow]")

    failed = False
    for c in commands:
        console.print(f"[dim]$ {c}[/dim]")
        exit_code = backend.exec(name, ["bash", "-c", c])
        if exit_code != 0:
            console.print(f"[red]Command failed with exit code {exit_code}:[/red] {c}")
            failed = True
            break

    if failed:
        console.print("[red]Reinstall failed. Network remains restricted.[/red]")
        console.print(f"[dim]To restore network access: raven network policy {name} open[/dim]")
        raise typer.Exit(1)

    console.print(f"[bold]Restoring {previous_phase.value} phase...[/bold]")
    try:
        backend.apply_network_phase(name, previous_phase)
    except Exception as e:
        log.warning("Could not restore network rules: %s", e)

    console.print("[green]Reinstall completed successfully.[/green]")


def run_cmd(
    name: str = typer.Argument(help="Environment name."),
    command: list[str] = typer.Argument(help="Command to run inside the environment."),
    workdir: Optional[str] = typer.Option(None, "--workdir", "-w", help="Working directory."),
    user: Optional[str] = typer.Option(None, "--user", "-u", help="User to run as."),
) -> None:
    """Run a command inside an environment."""
    backend, _ = _get_backend_for_env(name)
    state = load_state(name)

    if state.status != EnvStatus.RUNNING:
        console.print(f"[yellow]Environment '{name}' is not running. Starting...[/yellow]")
        backend.start(name)

    exit_code = backend.exec(
        name,
        command,
        workdir=workdir,
        user=user,
        tty=True,
        interactive=True,
    )
    raise typer.Exit(exit_code)
