"""Raven CLI entry point."""

from __future__ import annotations

import logging
try:
    import readline  # noqa: F401
except ImportError:
    pass

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
from raven.cli.env_commands import destroy, restart, shell, start, stop, purge  # noqa: E402
from raven.cli.run import run_cmd  # noqa: E402
from raven.cli.list_cmd import list_cmd, ps  # noqa: E402
from raven.cli.code import code  # noqa: E402
from raven.cli.top_cmd import top  # noqa: E402
from raven.cli.export_cmd import export  # noqa: E402
from raven.cli.init_cmd import init  # noqa: E402
from raven.cli.edit_cmd import edit  # noqa: E402
from raven.cli.logs_cmd import logs  # noqa: E402
from raven.cli.setup_cmd import setup  # noqa: E402
from raven.cli.status_cmd import status  # noqa: E402
from raven.cli.guard import guard_cmd, allow  # noqa: E402
from raven.cli.fw import fw_cmd  # noqa: E402
from raven.cli.config_cmd import config_app  # noqa: E402

app.command(name="create")(create)
app.command(name="init")(init)
app.command(name="setup")(setup)
app.command(name="edit")(edit)
app.command(name="start")(start)
app.command(name="stop")(stop)
app.command(name="restart")(restart)
app.command(name="shell")(shell)
app.command(name="destroy")(destroy)
app.command(name="purge")(purge)
app.command(name="run")(run_cmd)
app.command(name="list")(list_cmd)
app.command(name="ls")(list_cmd)
app.command(name="status")(status)
app.command(name="show")(status)
app.command(name="logs")(logs)
app.command(name="code")(code)
app.command(name="top")(top)
app.command(name="ps")(ps)
app.command(name="export")(export)
app.command(name="guard")(guard_cmd)
app.command(name="fw")(fw_cmd)
app.command(name="allow")(allow)
app.add_typer(config_app, name="config")


def main_entry() -> None:
    app()
