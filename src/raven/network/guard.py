"""Guard system for environment network isolation."""

from __future__ import annotations

import logging
import yaml
from pathlib import Path
from rich.table import Table

from raven.config.defaults import DEFAULT_REGISTRIES, KNOWN_CDN_CIDRS
from raven.config.schema import NetworkConfig
from raven.network.allowlists import resolve_allowlist, save_resolved_ips
from raven.network.nftables import (
    apply_rules,
    delete_table,
    generate_block_rules,
    generate_install_rules,
)
from raven.util.console import console
from raven.util.xdg import presets_dir

log = logging.getLogger(__name__)

BUILTIN_PRESETS = ("open", "offline", "registries", "restricted")


def resolve_preset(preset_name: str, network_config: NetworkConfig) -> list[str]:
    """Resolve a preset name to a list of allowed CIDRs.

    Resolution order:
    1. <preset_name>.yaml in current directory.
    2. <preset_name>.yaml in ~/.local/share/raven/presets/.
    3. Built-in presets.
    """
    # 1. Current directory
    local_path = Path.cwd() / f"{preset_name}.yaml"
    if local_path.exists():
        return _load_preset_file(local_path)

    # 2. Global presets folder
    global_path = presets_dir() / f"{preset_name}.yaml"
    if global_path.exists():
        return _load_preset_file(global_path)

    # 3. Built-ins
    if preset_name == "open":
        return []  # Special case: delete rules
    if preset_name == "offline":
        return []  # Special case: block all
    if preset_name == "registries":
        return resolve_allowlist(DEFAULT_REGISTRIES)
    if preset_name == "restricted":
        return resolve_allowlist(network_config.allowed_hosts)

    raise ValueError(f"Unknown guard preset: {preset_name}")


def _load_preset_file(path: Path) -> list[str]:
    """Load allowed hosts from a YAML file."""
    try:
        data = yaml.safe_load(path.read_text())
        if isinstance(data, list):
            return resolve_allowlist(data)
        if isinstance(data, dict) and "allowed_hosts" in data:
            return resolve_allowlist(data["allowed_hosts"])
        raise ValueError(f"Invalid preset file format in {path}")
    except Exception as e:
        log.error("Failed to load preset from %s: %s", path, e)
        raise ValueError(f"Failed to load preset from {path}: {e}")


def apply_guard(
    env_name: str,
    preset_name: str,
    network_config: NetworkConfig,
    pid: int,
) -> None:
    """Apply network rules for a given preset.

    Args:
        env_name: Environment name.
        preset_name: Name of the preset to apply.
        network_config: Network configuration from the environment config.
        pid: PID of a process running inside the container's network namespace.
    """
    log.info("Applying guard '%s' to environment '%s'", preset_name, env_name)

    if preset_name == "open":
        delete_table(env_name, pid)
        log.info("Guard applied: open network")
        return

    if preset_name == "offline":
        rule_file = generate_block_rules(env_name)
        apply_rules(rule_file, env_name, pid)
        log.info("Guard applied: network offline")
        return

    # For registries, restricted, or custom presets:
    console.print(f"[bold]Resolving guard allowlist: [cyan]{preset_name}[/cyan]...[/bold]")
    cidrs = resolve_preset(preset_name, network_config)
    save_resolved_ips(env_name, cidrs)
    
    console.print(f"Applying [green]{len(cidrs)}[/green] allowed CIDRs...")
    rule_file = generate_install_rules(env_name, cidrs)
    apply_rules(rule_file, env_name, pid)
    log.info("Guard applied: %s (%d CIDRs allowed)", preset_name, len(cidrs))


def show_guard_status(env_name: str, preset_name: str, network_config: NetworkConfig) -> None:
    """Display information about the current guard."""
    if preset_name in ("open", "offline"):
        console.print(f"Active Guard: [bold cyan]{preset_name}[/bold cyan]")
        return

    cidrs = resolve_preset(preset_name, network_config)
    console.print(f"Active Guard: [bold cyan]{preset_name}[/bold cyan] ([green]{len(cidrs)}[/green] CIDRs allowed)")
