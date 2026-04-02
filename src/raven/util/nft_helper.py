"""Root-owned helper to safely apply nftables rules inside a container's network namespace.

This script is intended to be run via sudo with strict validation to prevent
unauthorized access to other network namespaces or arbitrary nft rule application.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Entry point for raven-nft-helper."""
    if len(sys.argv) < 3:
        usage()
        sys.exit(1)

    action = sys.argv[1]
    env_name = sys.argv[2]

    # 1. Validate environment name (prevents path injection/traversal)
    if not re.match(r"^[a-zA-Z0-9_-]+$", env_name):
        print(f"Error: Invalid environment name '{env_name}'", file=sys.stderr)
        sys.exit(1)

    # 2. Get and validate PID
    try:
        pid = int(sys.argv[3])
    except (IndexError, ValueError):
        print("Error: Missing or invalid PID", file=sys.stderr)
        sys.exit(1)

    netns = f"/proc/{pid}/ns/net"
    if not os.path.exists(netns):
        print(f"Error: Network namespace {netns} not found", file=sys.stderr)
        sys.exit(1)

    # 3. Perform action
    if action == "apply":
        if len(sys.argv) < 5:
            print("Error: 'apply' requires a rule_file argument", file=sys.stderr)
            sys.exit(1)

        rule_file = sys.argv[4]
        rule_path = Path(rule_file).resolve()

        # SECURITY: Rule file MUST follow the naming convention for this environment
        if not rule_path.name.startswith(f"raven-{env_name}-") or not rule_path.name.endswith(".nft"):
            print(
                f"Error: Rule file name '{rule_path.name}' does not match environment '{env_name}'",
                file=sys.stderr,
            )
            sys.exit(1)

        # SECURITY: Rule file MUST be in a 'raven/nft-rules' directory to prevent
        # applying arbitrary user files from outside the raven data root.
        if "raven/nft-rules" not in str(rule_path):
            print("Error: Rule file must be located within a 'raven/nft-rules' directory",
                  file=sys.stderr)
            sys.exit(1)

        if not rule_path.exists():
            print(f"Error: Rule file {rule_path} does not exist", file=sys.stderr)
            sys.exit(1)

        # Execute: nsenter --net=/proc/<pid>/ns/net nft -f <path>
        cmd = ["nsenter", f"--net={netns}", "nft", "-f", str(rule_path)]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error: Failed to apply rules: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "delete":
        table_name = f"raven-{env_name}"
        # Execute: nsenter --net=/proc/<pid>/ns/net nft delete table inet raven-<env_name>
        cmd = ["nsenter", f"--net={netns}", "nft", "delete", "table", "inet", table_name]
        # delete table can fail if the table doesn't exist (e.g. already deleted), so we don't check
        subprocess.run(cmd, check=False)

    else:
        print(f"Error: Unknown action '{action}'", file=sys.stderr)
        usage()
        sys.exit(1)


def usage() -> None:
    """Print usage information."""
    print("Usage: raven-nft-helper apply <env_name> <pid> <rule_file>", file=sys.stderr)
    print("       raven-nft-helper delete <env_name> <pid>", file=sys.stderr)


if __name__ == "__main__":
    main()
