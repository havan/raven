"""Raven CLI entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from raven import __version__
from raven.util.log import setup_logging
from raven.util.xdg import logs_dir

app = typer.Typer(
    name="raven",
    help="Isolated development environments with supply-chain attack protection.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"raven {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show INFO-level messages."),
    debug: bool = typer.Option(False, "--debug", help="Show DEBUG-level messages (implies --verbose)."),
    log_file: Optional[Path] = typer.Option(None, "--log-file", help="Write structured log to this file (default: ~/.local/share/raven/logs/raven.log)."),
    version: bool = typer.Option(False, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version and exit."),
) -> None:
    """Raven — Isolated dev environments with SCA protection."""
    setup_logging(verbose=verbose, debug=debug, log_file=log_file or logs_dir() / "raven.log")


# Import and register sub-commands
from raven.cli.create import create  # noqa: E402
from raven.cli.env_commands import destroy, install, reinstall, run_cmd, shell, start, stop  # noqa: E402
from raven.cli.list_cmd import list_envs  # noqa: E402
from raven.cli.code import code  # noqa: E402
from raven.cli.ps import ps  # noqa: E402
from raven.cli.export_cmd import export
from raven.cli.init_cmd import init
from raven.cli.edit_cmd import edit
from raven.cli.logs_cmd import logs
from raven.cli.setup_cmd import setup
from raven.cli.status_cmd import status
from raven.cli.network_cmd import allow, network_app
from raven.cli.config_cmd import config_app

app.command(name="create")(create)
app.command(name="init")(init)
app.command(name="setup")(setup)
app.command(name="edit")(edit)
app.command(name="start")(start)
app.command(name="stop")(stop)
app.command(name="shell")(shell)
app.command(name="destroy")(destroy)
app.command(name="install")(install)
app.command(name="reinstall")(reinstall)
app.command(name="run")(run_cmd)
app.command(name="list")(list_envs)
app.command(name="status")(status)
app.command(name="logs")(logs)
app.command(name="code")(code)
app.command(name="ps")(ps)
app.command(name="export")(export)
app.add_typer(network_app, name="network")
app.add_typer(config_app, name="config")
app.command(name="allow")(allow)


def main_entry() -> None:
    app()
