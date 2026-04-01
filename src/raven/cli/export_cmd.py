"""raven export — export environment config for portability."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
import yaml

from raven.config.loader import load_config
from raven.util.console import console
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)


def export(
    name: str = typer.Argument(help="Environment name."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Write to file instead of stdout."),
    portable: bool = typer.Option(False, "--portable", help="Replace absolute paths with relative paths."),
) -> None:
    """Export an environment's YAML config for reproduction on another machine."""
    config_path = env_dir(name) / "config.yaml"
    config = load_config(config_path)

    data = config.model_dump(mode="json")

    if portable:
        # Replace absolute source paths with relative placeholder
        if "source" in data and data["source"].get("type") == "mount":
            data["source"]["path"] = "./project"

    yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)

    if output:
        output.write_text(yaml_str)
        console.print(f"[green]Config exported to {output}[/green]")
    else:
        sys.stdout.write(yaml_str)
