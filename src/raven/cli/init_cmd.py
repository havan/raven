"""raven init — initialize a new environment by cloning a repo."""

from __future__ import annotations

import logging
import re
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
from raven.util.xdg import ensure_dirs, env_dir, git_root, templates_dir

log = logging.getLogger(__name__)

DEFAULT_TEMPLATES = {
    "npm.yaml": {
        "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
        "setup_commands": ["cd /workspace && npm ci"],
    },
    "yarn.yaml": {
        "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
        "setup_commands": ["cd /workspace && yarn install"],
    },
    "pnpm.yaml": {
        "image": "mcr.microsoft.com/devcontainers/base:ubuntu",
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


def _parse_git_url(url: str) -> tuple[str, str]:
    """Return (owner, repo) parsed from a git URL.

    Handles HTTPS (https://github.com/owner/repo[.git]) and
    SSH (git@github.com:owner/repo[.git]) formats.
    """
    cleaned = re.sub(r"\.git$", "", url.rstrip("/"))
    # SSH: anything@host:owner/repo
    m = re.match(r"^[^@]+@[^:]+:(.+)$", cleaned)
    if m:
        path = m.group(1)
    else:
        # HTTPS or bare host/path — strip protocol then take last two segments
        path = re.sub(r"^[a-z+]+://", "", cleaned)

    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return "unknown", parts[-1] if parts else "repo"


def detect_template(workspace_path: Path) -> Optional[str]:
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
    return None


def init(
    name: str = typer.Argument(..., help="Environment name."),
    git_url: str = typer.Argument(..., help="Git URL to clone."),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="Template name to use (e.g. npm, yarn)."),
) -> None:
    """Clone a repository, generate a config, and create the environment."""
    ensure_dirs()
    ensure_templates()

    e_dir = env_dir(name)

    if e_dir.exists():
        console.print(f"[red]Error:[/red] Environment '{name}' already exists at {e_dir}")
        raise typer.Exit(1)

    e_dir.mkdir(parents=True, exist_ok=True)

    # 1. Determine workspace path under git root
    owner, repo = _parse_git_url(git_url)
    workspace_dir = git_root() / owner / repo
    workspace_dir.parent.mkdir(parents=True, exist_ok=True)

    if workspace_dir.exists():
        console.print(f"[yellow]Note:[/yellow] Workspace already exists at {workspace_dir} — skipping clone.")
    else:
        console.print(f"Cloning {git_url} into {workspace_dir}...")
        try:
            subprocess.run(["git", "clone", git_url, str(workspace_dir)], check=True)
        except subprocess.CalledProcessError:
            console.print("[red]Error:[/red] Git clone failed.")
            raise typer.Exit(1)

    # 2. Determine template
    selected_template = template or detect_template(workspace_dir)
    if not selected_template:
        console.print("\n[bold]No project template detected.[/bold]")
        _tpl_choices = sorted(list(set(t.split(".")[0] for t in DEFAULT_TEMPLATES.keys())))
        for i, t in enumerate(_tpl_choices, 1):
            console.print(f"  {i}. [cyan]{t}[/cyan]")
        _raw_tpl = typer.prompt("Choose template (number or name)", default="1")
        try:
            idx = int(_raw_tpl) - 1
            if idx < 0 or idx >= len(_tpl_choices):
                raise IndexError
            selected_template = _tpl_choices[idx]
        except (ValueError, IndexError):
            selected_template = _raw_tpl if _raw_tpl in _tpl_choices else "npm"

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

    # 3. Prompt for run-phase network policy
    _policy_choices = ["open", "restricted", "offline"]
    _policy_descriptions = {
        "open": "Full internet access",
        "restricted": "Only allowed hosts (configure with raven allow)",
        "offline": "No outbound network access",
    }
    console.print("\n[bold]Run phase network policy:[/bold]")
    for i, p in enumerate(_policy_choices, 1):
        console.print(f"  {i}. [cyan]{p}[/cyan] — {_policy_descriptions[p]}")

    _raw_policy = typer.prompt("Choose policy (number or name)", default="1")
    try:
        idx = int(_raw_policy) - 1
        if idx < 0 or idx >= len(_policy_choices):
            raise IndexError
        _chosen_policy = _policy_choices[idx]
    except (ValueError, IndexError):
        _chosen_policy = _raw_policy if _raw_policy in _policy_choices else "open"

    _initial_allowed_hosts: list[str] = []
    if _chosen_policy == "restricted":
        _hosts_raw = typer.prompt(
            "Initial allowed hosts (comma-separated, or Enter to skip)", default=""
        )
        if _hosts_raw.strip():
            _initial_allowed_hosts = [h.strip() for h in _hosts_raw.split(",") if h.strip()]

    # 4. Construct Config
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

    # Apply chosen run-phase policy (overrides any template default)
    cfg_dict.setdefault("network", {})
    cfg_dict["network"].setdefault("run_phase", {})
    cfg_dict["network"]["run_phase"]["policy"] = _chosen_policy
    if _initial_allowed_hosts:
        cfg_dict["network"]["run_phase"]["allowed_hosts"] = _initial_allowed_hosts

    try:
        cfg = EnvConfig.model_validate(cfg_dict)
    except ValidationError as e:
        console.print(f"[red]Configuration validation error:[/red]\n{e}")
        raise typer.Exit(1)

    # 5. Save Config
    config_path = save_config(cfg, e_dir / "config.yaml")

    # 6. Create Environment
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
        f"[dim]Run policy:[/dim] {_chosen_policy}\n"
        f"[dim]Workspace:[/dim] {workspace_dir}\n"
        f"[dim]Config:[/dim] {config_path}\n"
        f"[dim]Container:[/dim] {container_id}",
        title="raven init",
        border_style="green",
    ))
    console.print(f"You can now run [cyan]raven start {name}[/cyan] or [cyan]raven install {name}[/cyan].")
