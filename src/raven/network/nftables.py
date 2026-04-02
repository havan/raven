"""Generate and apply nftables rules for network isolation."""

from __future__ import annotations

import logging
from pathlib import Path

from raven.util.subprocess import run_as_root
from raven.util.xdg import nft_rules_dir

log = logging.getLogger(__name__)


def generate_install_rules(env_name: str, cidrs: list[str]) -> Path:
    """Generate nftables rule file for install phase (allowlist only).

    Rules are applied inside the container's network namespace (OUTPUT chain).

    Args:
        env_name: Environment name.
        cidrs: List of allowed CIDR strings.

    Returns:
        Path to the generated .nft file.
    """
    table_name = f"raven-{env_name}"

    ip_elements = ", ".join(cidrs) if cidrs else "0.0.0.0/32"  # dummy if empty

    rules = f"""\
table inet {table_name} {{

    set allowed_ips {{
        type ipv4_addr
        flags interval
        elements = {{ {ip_elements} }}
    }}

    chain output {{
        type filter hook output priority filter; policy accept;

        # Allow loopback
        oifname "lo" accept

        # Allow traffic to allowed IPs
        ip daddr @allowed_ips accept

        # Allow DNS (needed for hostname resolution)
        udp dport 53 accept
        tcp dport 53 accept

        # Allow established/related return traffic
        ct state established,related accept

        # Drop everything else
        drop
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
    """Generate nftables rules that block all outbound traffic.

    Rules are applied inside the container's network namespace (OUTPUT chain).
    """
    table_name = f"raven-{env_name}"

    rules = f"""\
table inet {table_name} {{
    chain output {{
        type filter hook output priority filter; policy drop;
        oifname "lo" accept
    }}
}}
"""

    rules_dir = nft_rules_dir()
    rules_dir.mkdir(parents=True, exist_ok=True)
    path = rules_dir / f"raven-{env_name}-block.nft"
    path.write_text(rules)
    log.info("Generated block rules: %s", path)
    return path


def apply_rules(rule_file: Path, env_name: str, pid: int) -> None:
    """Apply nftables rules inside the container's network namespace.

    Deletes the table first so the load is always against a clean slate.

    Args:
        rule_file: Path to the .nft file to apply.
        env_name: Environment name (used to delete any existing table first).
        pid: PID of a process in the container's network namespace.
    """
    netns = f"/proc/{pid}/ns/net"
    delete_table(env_name, pid)
    log.info("Applying nftables rules in netns %s: %s", netns, rule_file)
    run_as_root(["nsenter", f"--net={netns}", "nft", "-f", str(rule_file)])


def delete_table(env_name: str, pid: int) -> None:
    """Delete the nftables table inside the container's network namespace."""
    table_name = f"raven-{env_name}"
    netns = f"/proc/{pid}/ns/net"
    log.info("Deleting nftables table %s in netns %s", table_name, netns)
    run_as_root(
        ["nsenter", f"--net={netns}", "nft", "delete", "table", "inet", table_name],
        check=False,
    )


def cleanup_rule_files(env_name: str) -> None:
    """Remove all nftables rule files for an environment."""
    rules_dir = nft_rules_dir()
    for path in rules_dir.glob(f"raven-{env_name}-*.nft"):
        path.unlink()
        log.debug("Removed rule file: %s", path)
