"""Generate and apply nftables rules for network isolation."""

from __future__ import annotations

import logging
from pathlib import Path

from raven.util.subprocess import run_as_root
from raven.util.xdg import nft_rules_dir

log = logging.getLogger(__name__)


def generate_install_rules(env_name: str, cidrs: list[str]) -> Path:
    """Generate nftables rule file for install phase (allowlist only).

    Args:
        env_name: Environment name.
        cidrs: List of allowed CIDR strings.

    Returns:
        Path to the generated .nft file.
    """
    table_name = f"raven-{env_name}"
    iface = f"raven-{env_name}"  # Podman bridge interface name

    ip_elements = ", ".join(cidrs) if cidrs else "0.0.0.0/32"  # dummy if empty

    rules = f"""\
table inet {table_name} {{

    set allowed_ips {{
        type ipv4_addr
        flags interval
        elements = {{ {ip_elements} }}
    }}

    chain forward {{
        type filter hook forward priority filter; policy accept;

        # Allow traffic from this env to allowed IPs
        iifname "{iface}" ip daddr @allowed_ips accept

        # Allow DNS (needed for hostname resolution)
        iifname "{iface}" udp dport 53 accept
        iifname "{iface}" tcp dport 53 accept

        # Allow established/related return traffic
        iifname "{iface}" ct state established,related accept

        # Drop everything else from this env
        iifname "{iface}" drop
    }}
}}
"""

    rules_dir = nft_rules_dir()
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / f"raven-{env_name}-install.nft"
    path.write_text(rules)
    log.info("Generated nftables rules: %s", path)
    return path


def generate_block_rules(env_name: str) -> Path:
    """Generate nftables rules that block all outbound traffic."""
    table_name = f"raven-{env_name}"
    iface = f"raven-{env_name}"

    rules = f"""\
table inet {table_name} {{
    chain forward {{
        type filter hook forward priority filter; policy accept;
        iifname "{iface}" ct state established,related accept
        iifname "{iface}" drop
    }}
}}
"""

    rules_dir = nft_rules_dir()
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / f"raven-{env_name}-block.nft"
    path.write_text(rules)
    log.info("Generated block rules: %s", path)
    return path


def apply_rules(rule_file: Path) -> None:
    """Apply nftables rules from a file using sudo."""
    log.info("Applying nftables rules: %s", rule_file)
    run_as_root(["nft", "-f", str(rule_file)])


def delete_table(env_name: str) -> None:
    """Delete the nftables table for an environment (open network)."""
    table_name = f"raven-{env_name}"
    log.info("Deleting nftables table: %s", table_name)
    run_as_root(["nft", "delete", "table", "inet", table_name], check=False)


def cleanup_rule_files(env_name: str) -> None:
    """Remove all nftables rule files for an environment."""
    rules_dir = nft_rules_dir()
    for path in rules_dir.glob(f"raven-{env_name}-*.nft"):
        path.unlink()
        log.debug("Removed rule file: %s", path)
