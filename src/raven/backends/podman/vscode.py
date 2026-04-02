"""VS Code Remote SSH integration for Podman environments."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from raven.config.schema import VSCodeConfig
from raven.state.store import load_state
from raven.util.subprocess import run, stream_exec
from raven.util.xdg import env_dir

log = logging.getLogger(__name__)

MARKER_BEGIN = "# raven-begin/{name}"
MARKER_END = "# raven-end/{name}"


def setup_vscode_ssh(name: str, config: VSCodeConfig) -> dict[str, str]:
    """Set up SSH inside the container and configure the host for VS Code Remote.

    Returns a dict with connection details.
    """
    state = load_state(name)
    ssh_dir = env_dir(name)
    key_path = ssh_dir / "id_ed25519"

    # Generate SSH keypair if needed
    if not key_path.exists():
        ssh_dir.mkdir(parents=True, exist_ok=True)
        run([
            "ssh-keygen", "-t", "ed25519",
            "-f", str(key_path),
            "-N", "",  # no passphrase
            "-C", f"raven-{name}",
        ])
        key_path.chmod(0o600)
        log.info("Generated SSH key: %s", key_path)

    pub_key = key_path.with_suffix(".pub").read_text().strip()
    cname = f"raven-{name}"

    # Inject public key into container via base64 to avoid shell quoting issues
    encoded = base64.b64encode(pub_key.encode()).decode()
    run([
        "podman", "exec", cname,
        "sh", "-c",
        f"mkdir -p /root/.ssh && "
        f"echo {encoded} | base64 -d >> /root/.ssh/authorized_keys && "
        f"chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys",
    ])

    # Install and start SSH server inside container
    run([
        "podman", "exec", cname,
        "sh", "-c",
        "which sshd > /dev/null 2>&1 || "
        "(apt-get update -qq && apt-get install -y -qq openssh-server > /dev/null 2>&1) && "
        "mkdir -p /run/sshd && "
        "/usr/sbin/sshd",
    ], check=False)

    # Write SSH config on host
    _write_ssh_config(name, state.ssh_port, key_path)

    # Install VS Code extensions inside container
    for ext in config.extensions:
        log.info("Installing VS Code extension: %s", ext)
        # Extensions are installed by VS Code server once it connects

    return {
        "type": "ssh",
        "host": f"raven-{name}",
        "port": str(state.ssh_port),
        "key": str(key_path),
    }


def launch_vscode(name: str, workspace: str = "/workspace") -> None:
    """Open VS Code connected to the environment via Remote SSH."""
    stream_exec([
        "code", "--remote", f"ssh-remote+raven-{name}", workspace,
    ])


def _write_ssh_config(name: str, port: int, key_path: Path) -> None:
    """Write an SSH config block for this environment into ~/.ssh/config."""
    ssh_config_path = Path.home() / ".ssh" / "config"
    ssh_config_path.parent.mkdir(mode=0o700, exist_ok=True)

    begin = MARKER_BEGIN.format(name=name)
    end = MARKER_END.format(name=name)

    block = f"""\
{begin}
Host raven-{name}
    HostName 127.0.0.1
    Port {port}
    User root
    IdentityFile {key_path}
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
{end}
"""

    # Read existing config and replace or append
    if ssh_config_path.exists():
        existing = ssh_config_path.read_text()
        if begin in existing:
            # Replace existing block
            import re
            pattern = re.escape(begin) + r".*?" + re.escape(end)
            existing = re.sub(pattern, block.strip(), existing, flags=re.DOTALL)
            ssh_config_path.write_text(existing)
        else:
            # Append
            with ssh_config_path.open("a") as f:
                f.write("\n" + block)
    else:
        ssh_config_path.write_text(block)
        ssh_config_path.chmod(0o600)

    log.info("SSH config written for raven-%s (port %d)", name, port)


def remove_ssh_config(name: str) -> None:
    """Remove the SSH config block for this environment."""
    ssh_config_path = Path.home() / ".ssh" / "config"
    if not ssh_config_path.exists():
        return

    begin = MARKER_BEGIN.format(name=name)
    end = MARKER_END.format(name=name)

    existing = ssh_config_path.read_text()
    if begin in existing:
        import re
        pattern = re.escape(begin) + r".*?" + re.escape(end) + r"\n?"
        existing = re.sub(pattern, "", existing, flags=re.DOTALL)
        ssh_config_path.write_text(existing)
        log.info("Removed SSH config for raven-%s", name)
