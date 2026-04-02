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
    pid: int,
) -> None:
    """Switch the network rules for an environment between install and run phases.

    Rules are applied inside the container's network namespace (identified by pid).

    Args:
        env_name: Environment name.
        phase: Target phase.
        network_config: Network configuration from the environment config.
        pid: PID of a process running inside the container's network namespace.
    """
    if phase == NetworkPhase.INSTALL:
        switch_to_install(env_name, network_config, pid)
    elif phase == NetworkPhase.RUN:
        switch_to_run(env_name, network_config, pid)
    else:
        raise ValueError(f"Unknown network phase: {phase}")


def switch_to_install(env_name: str, network_config: NetworkConfig, pid: int) -> None:
    """Apply install-phase network rules (allowlist only)."""
    log.info("Switching '%s' to install phase (restricted network)", env_name)

    registries = network_config.install_phase.allowed_hosts
    cidrs = resolve_allowlist(registries)
    save_resolved_ips(env_name, cidrs)

    rule_file = generate_install_rules(env_name, cidrs)
    apply_rules(rule_file, env_name, pid)
    log.info("Install phase active: %d CIDRs allowed", len(cidrs))


def switch_to_run(env_name: str, network_config: NetworkConfig, pid: int) -> None:
    """Apply run-phase network rules based on policy."""
    policy = network_config.run_phase.policy
    log.info("Switching '%s' to run phase (policy: %s)", env_name, policy)

    if policy == "open":
        # Remove all restrictions
        delete_table(env_name, pid)
        log.info("Run phase active: open network")

    elif policy in ("restricted", "allowlist"):
        hosts = network_config.run_phase.allowed_hosts
        cidrs = resolve_allowlist(hosts)
        save_resolved_ips(env_name, cidrs)
        rule_file = generate_install_rules(env_name, cidrs)
        apply_rules(rule_file, env_name, pid)
        log.info("Run phase active: %d CIDRs allowed", len(cidrs))

    elif policy in ("offline", "block"):
        rule_file = generate_block_rules(env_name)
        apply_rules(rule_file, env_name, pid)
        log.info("Run phase active: network offline")

    else:
        raise ValueError(f"Unknown run phase policy: {policy}")
