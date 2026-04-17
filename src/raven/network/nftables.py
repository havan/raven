"""Generate and apply nftables rules for network isolation."""

from __future__ import annotations

import logging
from pathlib import Path

from raven.util.subprocess import run_as_root
from raven.util.xdg import nft_rules_dir

log = logging.getLogger(__name__)


def generate_install_rules(env_name: str, cidrs: list[str], resolvers: list[str] | None = None) -> Path:
    """Generate nftables rule file for install phase (allowlist only).

    Rules are applied inside the container's network namespace (OUTPUT chain).

    Args:
        env_name: Environment name.
        cidrs: List of allowed CIDR strings.
        resolvers: List of trusted resolver IP addresses. If None,
                  read from /etc/resolv.conf.

    Returns:
        Path to the generated .nft file.
    """
    table_name = f"raven-{env_name}"

    if resolvers is None:
        resolvers = _get_host_resolvers()

    ip_elements = ", ".join(cidrs) if cidrs else "0.0.0.0/32"  # dummy if empty

    # Only allow DNS if we have an allowlist (otherwise DNS is useless and a tunneling risk)
    dns_rules = ""
    if cidrs and resolvers:
        v4_resolvers = [r for r in resolvers if ":" not in r]
        v6_resolvers = [r for r in resolvers if ":" in r]
        
        dns_rules_list = ["        # Allow DNS (only to trusted resolvers)"]
        if v4_resolvers:
            v4_elements = ", ".join(v4_resolvers)
            dns_rules_list.append(f"        ip daddr {{ {v4_elements} }} udp dport 53 accept")
            dns_rules_list.append(f"        ip daddr {{ {v4_elements} }} tcp dport 53 accept")
        if v6_resolvers:
            v6_elements = ", ".join(v6_resolvers)
            dns_rules_list.append(f"        ip6 daddr {{ {v6_elements} }} udp dport 53 accept")
            dns_rules_list.append(f"        ip6 daddr {{ {v6_elements} }} tcp dport 53 accept")
        
        dns_rules = "\n".join(dns_rules_list) + "\n"
    elif cidrs:
        log.warning("No resolvers found for '%s' — DNS access will be blocked.", env_name)
    else:
        log.warning("Empty allowlist for '%s' — DNS access will be blocked.", env_name)

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
{dns_rules}
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


def _get_host_resolvers() -> list[str]:
    """Read nameservers from /etc/resolv.conf."""
    resolvers = []
    try:
        conf = Path("/etc/resolv.conf")
        if conf.exists():
            for line in conf.read_text().splitlines():
                if line.startswith("nameserver "):
                    resolvers.append(line.split()[1])
    except Exception:
        pass
    return resolvers


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

    Uses a root-owned helper script for security.

    Args:
        rule_file: Path to the .nft file to apply.
        env_name: Environment name.
        pid: PID of a process in the container's network namespace.
    """
    # Delete table first so the load is always against a clean slate.
    delete_table(env_name, pid)
    log.info("Applying nftables rules for '%s' (PID %d): %s", env_name, pid, rule_file)
    run_as_root(
        ["raven-nft-helper", "apply", env_name, str(pid), str(rule_file)],
        capture=False,
    )


def delete_table(env_name: str, pid: int) -> None:
    """Delete the nftables table inside the container's network namespace."""
    log.info("Deleting nftables table for '%s' (PID %d)", env_name, pid)
    # We don't capture output here because the helper handles its own silence
    # and we don't want to log harmless 'not found' errors in Raven's debug logs.
    run_as_root(
        ["raven-nft-helper", "delete", env_name, str(pid)],
        check=False,
        capture=False,
    )


def cleanup_rule_files(env_name: str) -> None:
    """Remove all nftables rule files for an environment."""
    rules_dir = nft_rules_dir()
    for path in rules_dir.glob(f"raven-{env_name}-*.nft"):
        path.unlink()
        log.debug("Removed rule file: %s", path)
