"""Root-owned helper to safely apply nftables rules inside a container's network namespace.

This script is intended to be run via sudo with strict validation to prevent
unauthorized access to other network namespaces or arbitrary nft rule application.
"""

from __future__ import annotations

import os
import pwd
import re
import subprocess
import sys
from pathlib import Path


def get_user_data_dir() -> Path:
    """Determine the raven data directory for the original user who invoked sudo."""
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        try:
            home = Path(pwd.getpwnam(sudo_user).pw_dir)
            return home / ".local" / "share" / "raven"
        except (KeyError, ImportError):
            pass
    # Fallback to current user (root or whatever is running)
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return Path(base) / "raven"


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

    # 3. Security: Cross-reference PID with Raven state
    data_root = get_user_data_dir()
    state_file = data_root / "envs" / env_name / "state.json"
    if not state_file.exists():
        print(f"Error: Environment state not found for '{env_name}' at {state_file}",
              file=sys.stderr)
        sys.exit(1)

    import json
    try:
        state_data = json.loads(state_file.read_text())
    except Exception as e:
        print(f"Error: Failed to parse state file for '{env_name}': {e}", file=sys.stderr)
        sys.exit(1)

    # Validate that this PID is indeed for this environment
    container_id = state_data.get("container_id")
    if not container_id:
        print(f"Error: State for '{env_name}' is missing container_id", file=sys.stderr)
        sys.exit(1)

    # Verification: check /proc/<pid>/cgroup for the container_id
    # Rootless Podman usually puts container ID in cgroup path
    try:
        cgroup_path = Path(f"/proc/{pid}/cgroup")
        if not cgroup_path.exists():
            print(f"Error: Process {pid} not found", file=sys.stderr)
            sys.exit(1)

        cgroup_content = cgroup_path.read_text()
        if container_id not in cgroup_content:
            # Fallback: check if the process is exactly 'sshd' and has our container_id
            # in its environment or similar, but cgroup is the most reliable.
            print(f"Error: Process {pid} does not belong to environment '{env_name}'",
                  file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error: Failed to verify PID {pid} against environment '{env_name}': {e}",
              file=sys.stderr)
        sys.exit(1)

    netns = f"/proc/{pid}/ns/net"
    if not os.path.exists(netns):
        print(f"Error: Network namespace {netns} not found", file=sys.stderr)
        sys.exit(1)

    # 4. Perform action
    if action == "apply":
        if len(sys.argv) < 5:
            print("Error: 'apply' requires a rule_file argument", file=sys.stderr)
            sys.exit(1)

        rule_file = sys.argv[4]
        rule_path = Path(rule_file).resolve()

        # SECURITY: Rule file MUST be within the exact Raven nft-rules directory
        expected_rules_dir = data_root / "nft-rules"
        if not str(rule_path).startswith(str(expected_rules_dir) + os.sep):
            print(f"Error: Rule file {rule_path} is not in {expected_rules_dir}", file=sys.stderr)
            sys.exit(1)

        # SECURITY: Rule file MUST follow the naming convention for this environment
        if not rule_path.name.startswith(f"raven-{env_name}-") or not rule_path.name.endswith(".nft"):
            print(
                f"Error: Rule file name '{rule_path.name}' does not match environment '{env_name}'",
                file=sys.stderr,
            )
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
        # delete table can fail if the table doesn't exist (e.g. already deleted),
        # so we capture output to keep it silent and don't check the exit code.
        subprocess.run(cmd, check=False, capture_output=True)

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
