"""DNS resolution and CIDR expansion for network allowlists."""

from __future__ import annotations

import logging
from ipaddress import IPv4Network

from raven.config.defaults import KNOWN_CDN_CIDRS

log = logging.getLogger(__name__)


def resolve_allowlist(hostnames: list[str]) -> list[str]:
    """Resolve hostnames to IP addresses/CIDRs for nftables rules.

    Uses known CDN CIDR ranges where available, falls back to DNS resolution.

    Returns:
        A deduplicated list of CIDR strings (e.g. ["104.16.0.0/12", "1.2.3.4/32"]).
    """
    cidrs: set[str] = set()

    for hostname in hostnames:
        # Check for known CDN range first
        if hostname in KNOWN_CDN_CIDRS:
            for cidr in KNOWN_CDN_CIDRS[hostname]:
                cidrs.add(cidr)
                log.debug("Using known CDN CIDR for %s: %s", hostname, cidr)
            continue

        # DNS resolution fallback
        try:
            import dns.resolver
            answers = dns.resolver.resolve(hostname, "A")
            for rdata in answers:
                cidr = f"{rdata.address}/32"
                cidrs.add(cidr)
                log.debug("Resolved %s -> %s", hostname, cidr)
        except Exception as e:
            log.warning("Could not resolve %s: %s", hostname, e)

    return sorted(cidrs)


def save_resolved_ips(env_name: str, cidrs: list[str]) -> None:
    """Cache resolved IPs to disk for later reference."""
    import json
    from raven.util.xdg import data_dir

    cache_dir = data_dir() / "networks"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"raven-{env_name}.json"
    cache_file.write_text(json.dumps({"cidrs": cidrs}, indent=2))
    log.debug("Cached resolved IPs: %s", cache_file)
