"""Network phase switching between install and run modes."""

from __future__ import annotations

import logging

from raven.config.schema import NetworkConfig
from raven.network.allowlists import resolve_allowlist, save_resolved_ips
from raven.network.nftables import (
    apply_rules,
    delete_table,
    generate_block_rules,
    generate_install_rules,
)
from raven.state.models import NetworkPhase

log = logging.getLogger(__name__)


def switch_phase(
    env_name: str,
    phase: NetworkPhase,
    network_config: NetworkConfig,
    iface: str,
) -> None:
    """Switch the network rules for an environment between install and run phases.

    Args:
        env_name: Environment name.
        phase: Target phase.
        network_config: Network configuration from the environment config.
        iface: Actual bridge interface name assigned by Podman/netavark.
    """
    if phase == NetworkPhase.INSTALL:
        switch_to_install(env_name, network_config, iface)
    elif phase == NetworkPhase.RUN:
        switch_to_run(env_name, network_config, iface)
    else:
        raise ValueError(f"Unknown network phase: {phase}")


def switch_to_install(env_name: str, network_config: NetworkConfig, iface: str) -> None:
    """Apply install-phase network rules (allowlist only)."""
    log.info("Switching '%s' to install phase (restricted network)", env_name)

    registries = network_config.install_phase.allowed_registries
    cidrs = resolve_allowlist(registries)
    save_resolved_ips(env_name, cidrs)

    rule_file = generate_install_rules(env_name, cidrs, iface)
    apply_rules(rule_file, env_name)
    log.info("Install phase active: %d CIDRs allowed", len(cidrs))


def switch_to_run(env_name: str, network_config: NetworkConfig, iface: str) -> None:
    """Apply run-phase network rules based on policy."""
    policy = network_config.run_phase.policy
    log.info("Switching '%s' to run phase (policy: %s)", env_name, policy)

    if policy == "open":
        # Remove all restrictions
        delete_table(env_name)
        log.info("Run phase active: open network")

    elif policy == "allowlist":
        hosts = network_config.run_phase.allowed_hosts
        cidrs = resolve_allowlist(hosts)
        rule_file = generate_install_rules(env_name, cidrs, iface)
        apply_rules(rule_file, env_name)
        log.info("Run phase active: %d CIDRs allowed", len(cidrs))

    elif policy == "block":
        rule_file = generate_block_rules(env_name, iface)
        apply_rules(rule_file, env_name)
        log.info("Run phase active: network blocked")

    else:
        raise ValueError(f"Unknown run phase policy: {policy}")
