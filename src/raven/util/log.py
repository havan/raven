"""Logging setup with rich handler and JSON Lines file output."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from rich.logging import RichHandler


class JSONLinesFormatter(logging.Formatter):
    """Format log records as JSON Lines for structured log files."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Include extra fields from record
        for key in ("env", "cmd", "phase", "rule_file"):
            if hasattr(record, key):
                entry[key] = getattr(record, key)
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = str(record.exc_info[1])
        return json.dumps(entry)


def setup_logging(
    verbose: bool = False,
    debug: bool = False,
    log_file: Path | None = None,
) -> None:
    """Configure logging for raven.

    Args:
        verbose: Show INFO-level messages.
        debug: Show DEBUG-level messages (implies verbose).
        log_file: Path to a JSON Lines log file.
    """
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING

    handlers: list[logging.Handler] = [
        RichHandler(
            rich_tracebacks=True,
            show_path=debug,
            show_time=debug,
            markup=True,
        )
    ]

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JSONLinesFormatter())
        file_handler.setLevel(logging.DEBUG)  # always log everything to file
        handlers.append(file_handler)

    logging.basicConfig(
        level=level,
        handlers=handlers,
        format="%(message)s",
        datefmt="[%X]",
        force=True,
    )
