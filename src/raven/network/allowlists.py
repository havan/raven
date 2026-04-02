"""DNS resolution and CIDR expansion for network allowlists."""

from __future__ import annotations

import logging
from ipaddress import collapse_addresses, ip_network

from raven.config.defaults import KNOWN_CDN_CIDRS

log = logging.getLogger(__name__)


def resolve_allowlist(hostnames: list[str]) -> list[str]:
    """Resolve hostnames to IP addresses/CIDRs for nftables rules.

    Uses known CDN CIDR ranges where available, falls back to DNS resolution.

    Returns:
        A deduplicated list of CIDR strings (e.g. ["104.16.0.0/12", "1.2.3.4/32"]).
    """
    cidrs: set[str] = set()

    # DNS resolution fallback
    try:
        import dns.exception
        import dns.resolver
        resolver = dns.resolver.Resolver()
        resolver.lifetime = 5.0  # 5 second timeout for resolution
    except ImportError:
        log.warning("dnspython not installed, DNS resolution fallback disabled.")
        resolver = None

    for hostname in hostnames:
        # Check for known CDN range first
        if hostname in KNOWN_CDN_CIDRS:
            for cidr in KNOWN_CDN_CIDRS[hostname]:
                cidrs.add(cidr)
                log.debug("Using known CDN CIDR for %s: %s", hostname, cidr)
            continue

        if not resolver:
            continue

        try:
            answers = resolver.resolve(hostname, "A")
            for rdata in answers:
                cidr = f"{rdata.address}/32"
                cidrs.add(cidr)
                log.debug("Resolved %s -> %s", hostname, cidr)
        except dns.exception.DNSException as e:
            log.warning("Could not resolve %s: %s", hostname, e)

    # Collapse overlapping/redundant prefixes (e.g. 104.16.0.0/12 subsumes 104.16.x.y/32)
    try:
        networks = [ip_network(c, strict=False) for c in cidrs]
        collapsed = collapse_addresses(networks)
        return [str(n) for n in collapsed]
    except Exception as e:
        log.warning("CIDR collapse failed, using raw list: %s", e)
        return sorted(cidrs)


def load_resolved_ips(env_name: str) -> list[str]:
    """Load cached resolved IPs from disk. Returns empty list if not found."""
    import json
    from raven.util.xdg import data_dir

    cache_file = data_dir() / "networks" / f"raven-{env_name}.json"
    if not cache_file.exists():
        return []
    try:
        return json.loads(cache_file.read_text()).get("cidrs", [])
    except Exception:
        return []


def save_resolved_ips(env_name: str, cidrs: list[str]) -> None:
    """Cache resolved IPs to disk for later reference."""
    import json
    from raven.util.xdg import data_dir

    cache_dir = data_dir() / "networks"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"raven-{env_name}.json"
    cache_file.write_text(json.dumps({"cidrs": cidrs}, indent=2))
    log.debug("Cached resolved IPs: %s", cache_file)
