"""raven init — initialize a new environment by cloning a repo."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Optional

import typer
import yaml
from pydantic import ValidationError
from rich.panel import Panel

from raven.backends import get_backend
from raven.config.loader import save_config
from raven.config.schema import EnvConfig
from raven.util.console import console
from raven.util.xdg import ensure_dirs, env_dir, templates_dir

log = logging.getLogger(__name__)

DEFAULT_TEMPLATES = {
    "npm.yaml": {
        "image": "node:22-bookworm-slim",
        "setup_commands": ["cd /workspace && npm ci"],
    },
    "yarn.yaml": {
        "image": "node:22-bookworm-slim",
        "setup_commands": ["cd /workspace && yarn install"],
    },
    "pnpm.yaml": {
        "image": "node:22-bookworm-slim",
        "setup_commands": ["cd /workspace && corepack enable pnpm && pnpm install"],
    },
    "uv.yaml": {
        "image": "python:3.12-slim",
        "setup_commands": [
            "cd /workspace && apt-get update && apt-get install -y curl",
            "cd /workspace && curl -LsSf https://astral.sh/uv/install.sh | sh",
            "cd /workspace && /root/.local/bin/uv sync",
        ],
    },
    "pip.yaml": {
        "image": "python:3.12-slim",
        "setup_commands": ["cd /workspace && pip install -r requirements.txt"],
    },
}


def ensure_templates() -> None:
    """Create default templates if they don't exist."""
    t_dir = templates_dir()
    for name, content in DEFAULT_TEMPLATES.items():
        t_path = t_dir / name
        if not t_path.exists():
            t_path.write_text(yaml.dump(content, default_flow_style=False, sort_keys=False))


def detect_template(workspace_path: Path) -> str:
    """Guess the package manager from lockfiles."""
    if (workspace_path / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (workspace_path / "yarn.lock").exists():
        return "yarn"
    if (workspace_path / "package-lock.json").exists():
        return "npm"
    if (workspace_path / "uv.lock").exists():
        return "uv"
    if (workspace_path / "requirements.txt").exists() or (workspace_path / "pyproject.toml").exists():
        return "pip"
    return "npm"  # Fallback


def init(
    name: str = typer.Argument(..., help="Environment name."),
    git_url: str = typer.Argument(..., help="Git URL to clone."),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="Template name to use (e.g. npm, yarn)."),
) -> None:
    """Clone a repository, generate a config, and create the environment."""
    ensure_dirs()
    ensure_templates()

    e_dir = env_dir(name)
    workspace_dir = e_dir / "workspace"

    if e_dir.exists():
        console.print(f"[red]Error:[/red] Environment '{name}' already exists at {e_dir}")
        raise typer.Exit(1)

    e_dir.mkdir(parents=True, exist_ok=True)

    # 1. Clone repository
    console.print(f"Cloning {git_url} into {workspace_dir}...")
    try:
        subprocess.run(["git", "clone", git_url, str(workspace_dir)], check=True)
    except subprocess.CalledProcessError:
        console.print("[red]Error:[/red] Git clone failed.")
        raise typer.Exit(1)

    # 2. Determine template
    selected_template = template or detect_template(workspace_dir)
    template_file = templates_dir() / f"{selected_template}.yaml"

    if not template_file.exists():
        console.print(f"[yellow]Warning:[/yellow] Template '{selected_template}' not found at {template_file}. Using basic defaults.")
        tpl_data = {}
    else:
        try:
            tpl_data = yaml.safe_load(template_file.read_text()) or {}
        except yaml.YAMLError as e:
            console.print(f"[red]Error parsing template {template_file}:[/red] {e}")
            raise typer.Exit(1)

    # 3. Construct Config
    cfg_dict = {
        "name": name,
        "source": {
            "type": "mount",
            "path": str(workspace_dir.absolute()),
            "mount_path": "/workspace",
        },
    }
    # Merge template data over base config
    cfg_dict.update(tpl_data)

    try:
        cfg = EnvConfig.model_validate(cfg_dict)
    except ValidationError as e:
        console.print(f"[red]Configuration validation error:[/red]\n{e}")
        raise typer.Exit(1)

    # 4. Save Config
    config_path = save_config(cfg, e_dir / "config.yaml")

    # 5. Create Environment
    backend = get_backend(cfg)
    console.print("Creating environment...")
    try:
        container_id = backend.create(cfg)
    except RuntimeError as e:
        console.print(f"[red]Error creating environment:[/red] {e}")
        raise typer.Exit(1)

    console.print(Panel(
        f"[bold green]Environment initialized and created:[/bold green] {cfg.name}\n"
        f"[dim]Template:[/dim] {selected_template}\n"
        f"[dim]Workspace:[/dim] {workspace_dir}\n"
        f"[dim]Config:[/dim] {config_path}\n"
        f"[dim]Container:[/dim] {container_id}",
        title="raven init",
        border_style="green",
    ))
    console.print(f"You can now run [cyan]raven start {name}[/cyan] or [cyan]raven install {name}[/cyan].")
