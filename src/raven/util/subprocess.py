"""Safe subprocess wrappers for raven."""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Any

log = logging.getLogger(__name__)


def run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess command and return the result.

    Args:
        cmd: Command and arguments.
        check: Raise CalledProcessError on non-zero exit.
        capture: Capture stdout/stderr (if False, inherits the terminal).
        **kwargs: Passed through to subprocess.run.
    """
    log.debug("Running: %s", " ".join(cmd))
    if capture:
        kwargs.setdefault("stdout", subprocess.PIPE)
        kwargs.setdefault("stderr", subprocess.PIPE)
    kwargs.setdefault("text", True)
    result = subprocess.run(cmd, check=check, **kwargs)
    if capture and result.stdout:
        log.debug("stdout: %s", result.stdout.strip())
    if capture and result.stderr:
        log.debug("stderr: %s", result.stderr.strip())
    return result


def run_as_root(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """Run a command with sudo (for nftables rule application)."""
    return run(["sudo"] + cmd, **kwargs)


def exec_replace(cmd: list[str]) -> None:
    """Replace the current process with the given command (for interactive shells)."""
    log.debug("exec: %s", " ".join(cmd))
    os.execvp(cmd[0], cmd)


def stream_exec(
    cmd: list[str],
    **kwargs: Any,
) -> int:
    """Run a command with inherited stdin/stdout/stderr and return exit code."""
    log.debug("Streaming: %s", " ".join(cmd))
    result = subprocess.run(cmd, check=False, **kwargs)
    return result.returncode
