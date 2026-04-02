from __future__ import annotations

import logging
import shutil

import typer

from raven.util.subprocess import stream_exec
from raven.util.xdg import quadlet_dir

log = logging.getLogger(__name__)


def logs(
    name: str = typer.Argument(..., help="Environment name."),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output."),
    lines: int = typer.Option(50, "--lines", "-n", help="Number of lines to show."),
) -> None:
    """Show logs for an environment."""
    quadlet_file = quadlet_dir() / f"raven-{name}.container"
    use_journalctl = quadlet_file.exists() and shutil.which("journalctl")

    if use_journalctl:
        log.debug("Using journalctl for systemd service raven-%s.service", name)
        cmd = ["journalctl", "--user", "-u", f"raven-{name}.service", "--no-pager", "-n", str(lines)]
        if follow:
            cmd.append("-f")
    else:
        log.debug("Using podman logs for container raven-%s", name)
        cmd = ["podman", "logs", f"raven-{name}", "--tail", str(lines)]
        if follow:
            cmd.append("--follow")

    try:
        exit_code = stream_exec(cmd)
        if exit_code != 0:
            # The command already streamed its output, so we just exit.
            raise typer.Exit(exit_code)
    except FileNotFoundError:
        log.error("Could not execute '%s'. Is it installed and in your PATH?", cmd[0])
        raise typer.Exit(1)
