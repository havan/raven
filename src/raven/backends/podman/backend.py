"""Podman backend implementation using Quadlet for systemd integration."""

from __future__ import annotations

import json
import logging
import socket
from datetime import datetime, timezone

from raven.backends.base import Backend, EnvInfo
from raven.backends.podman.systemd import (
    container_name,
    generate_container_service,
    network_name,
    remove_service_files,
)
from raven.config.schema import EnvConfig, SourceClone, VSCodeConfig
from raven.state.models import EnvState, EnvStatus, NetworkPhase
from raven.state.store import delete_state, load_state, save_state, state_exists
from raven.util.subprocess import exec_replace, run, stream_exec

log = logging.getLogger(__name__)

SERVICE_PREFIX = "raven-"


def _service_name(env_name: str) -> str:
    return f"raven-{env_name}"


def _find_free_port() -> int:
    """Find a free TCP port on localhost for SSH forwarding."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class PodmanBackend(Backend):
    """Rootless Podman backend using Quadlet for systemd lifecycle management."""

    def create(self, config: EnvConfig) -> str:
        cname = container_name(config.name)

        if state_exists(config.name):
            raise RuntimeError(
                f"Environment '{config.name}' already exists. "
                "Use 'raven destroy' first."
            )

        ssh_port = _find_free_port()
        log.info("Assigned SSH port %d for environment '%s'", ssh_port, config.name)

        # Create the podman network for this environment
        run([
            "podman", "network", "create",
            "--ignore",
            "--driver=bridge",
            "--label", f"raven.env={config.name}",
            "--label", "raven.managed=true",
            network_name(config.name),
        ])
        log.info("Created podman network '%s'", network_name(config.name))

        from raven.backends.podman.network import get_network_interface
        network_iface = get_network_interface(config.name)
        log.info("Network bridge interface: %s", network_iface)

        # Generate the systemd service unit
        generate_container_service(config, ssh_port)

        # Reload systemd to pick up new unit files
        run(["systemctl", "--user", "daemon-reload"])
        log.info("Systemd daemon reloaded")

        # Save initial state
        state = EnvState(
            name=config.name,
            container_id=cname,
            status=EnvStatus.CREATED,
            network_name=network_name(config.name),
            network_interface=network_iface,
            ssh_port=ssh_port,
            backend="podman",
        )
        save_state(state)

        # If source is clone, we'll handle that at start time
        log.info("Environment '%s' created (container: %s)", config.name, cname)
        return cname

    def start(self, name: str) -> None:
        state = load_state(name)
        if state.status == EnvStatus.RUNNING:
            # Verify it's actually running before trusting state
            if self.status(name) == EnvStatus.RUNNING:
                log.warning("Environment '%s' is already running", name)
                return
            log.warning("State says running but container is not — restarting")

        svc = _service_name(name)
        # Clear any previous failure state so systemd allows a fresh start
        run(["systemctl", "--user", "reset-failed", f"{svc}.service"], check=False)

        result = run(["systemctl", "--user", "start", f"{svc}.service"], check=False)
        if result.returncode != 0:
            err = (result.stderr or "").strip() or "(no stderr)"
            raise RuntimeError(
                f"Failed to start service '{svc}.service'.\n"
                f"Hint: systemctl --user status {svc}.service\n"
                f"systemd error: {err}"
            )

        # Wait for container to be running
        self._wait_for_running(name)

        state.status = EnvStatus.RUNNING
        state.started_at = datetime.now(timezone.utc).isoformat()
        save_state(state)
        log.info("Environment '%s' started", name)

    def stop(self, name: str, timeout: int = 10) -> None:
        state = load_state(name)
        if state.status == EnvStatus.STOPPED:
            log.warning("Environment '%s' is already stopped", name)
            return

        svc = _service_name(name)
        run(["systemctl", "--user", "stop", f"{svc}.service"], check=False)

        state.status = EnvStatus.STOPPED
        state.started_at = ""
        save_state(state)
        log.info("Environment '%s' stopped", name)

    def destroy(self, name: str) -> None:
        # Stop first
        try:
            self.stop(name)
        except FileNotFoundError:
            pass

        svc = _service_name(name)
        # Remove service unit files (and legacy Quadlet files if present)
        remove_service_files(name)
        run(["systemctl", "--user", "daemon-reload"])

        # Clean up the Podman network
        run(
            ["podman", "network", "rm", "-f", network_name(name)],
            check=False,
        )

        # Remove any leftover container
        run(
            ["podman", "rm", "-f", container_name(name)],
            check=False,
        )

        # Remove state
        delete_state(name)
        log.info("Environment '%s' destroyed", name)

    def exec(
        self,
        name: str,
        command: list[str],
        *,
        workdir: str | None = None,
        user: str | None = None,
        env: dict[str, str] | None = None,
        tty: bool = False,
        interactive: bool = False,
    ) -> int:
        cmd = ["podman", "exec"]
        if tty and interactive:
            cmd.append("-it")
        elif tty:
            cmd.append("-t")
        elif interactive:
            cmd.append("-i")
        if workdir:
            cmd.extend(["-w", workdir])
        if user:
            cmd.extend(["-u", user])
        if env:
            for k, v in env.items():
                cmd.extend(["-e", f"{k}={v}"])

        cmd.append(container_name(name))
        cmd.extend(command)

        if tty and interactive:
            # Replace process for interactive use
            exec_replace(cmd)
            return 0  # unreachable, but satisfies type checker
        else:
            return stream_exec(cmd)

    def shell(self, name: str, shell_binary: str = "/bin/bash") -> int:
        return self.exec(
            name,
            [shell_binary],
            tty=True,
            interactive=True,
        )

    def status(self, name: str) -> EnvStatus:
        result = run(
            [
                "podman", "inspect",
                "--format", "{{.State.Status}}",
                container_name(name),
            ],
            check=False,
        )
        if result.returncode != 0:
            return EnvStatus.UNKNOWN

        podman_status = result.stdout.strip().lower()
        status_map = {
            "running": EnvStatus.RUNNING,
            "exited": EnvStatus.STOPPED,
            "stopped": EnvStatus.STOPPED,
            "created": EnvStatus.CREATED,
            "paused": EnvStatus.STOPPED,
            "dead": EnvStatus.ERROR,
        }
        return status_map.get(podman_status, EnvStatus.UNKNOWN)

    def list_all(self) -> list[EnvInfo]:
        result = run(
            [
                "podman", "ps", "-a",
                "--filter", "label=raven.managed=true",
                "--format", "json",
            ],
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []

        containers = json.loads(result.stdout)
        if not isinstance(containers, list):
            containers = [containers]

        infos = []
        for c in containers:
            # Extract env name from label
            labels = c.get("Labels", {})
            env_name = labels.get("raven.env", c.get("Names", ["?"])[0])

            status_str = c.get("State", "unknown").lower()
            status_map = {
                "running": EnvStatus.RUNNING,
                "exited": EnvStatus.STOPPED,
                "created": EnvStatus.CREATED,
            }

            infos.append(EnvInfo(
                name=env_name,
                status=status_map.get(status_str, EnvStatus.UNKNOWN),
                backend="podman",
                image=c.get("Image", ""),
                created_at=c.get("Created", ""),
                ports=[str(p) for p in c.get("Ports", [])],
            ))
        return infos

    def get_info(self, name: str) -> EnvInfo:
        result = run(
            [
                "podman", "inspect", container_name(name),
                "--format", "json",
            ],
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Cannot inspect environment '{name}'")

        data = json.loads(result.stdout)
        if isinstance(data, list):
            data = data[0]

        return EnvInfo(
            name=name,
            status=self.status(name),
            backend="podman",
            image=data.get("ImageName", data.get("Image", "")),
            created_at=data.get("Created", ""),
        )

    def apply_network_phase(self, name: str, phase: NetworkPhase) -> None:
        from raven.config.loader import load_config
        from raven.network.phases import switch_phase
        from raven.util.xdg import env_dir

        state = load_state(name)
        config_path = env_dir(name) / "config.yaml"
        config = load_config(config_path)

        # Get the PID of a process inside the container's network namespace.
        # Rules are applied via nsenter into that netns.
        pid_result = run(
            ["podman", "inspect", "--format", "{{.State.Pid}}", container_name(name)],
            check=False,
        )
        if pid_result.returncode != 0 or not pid_result.stdout.strip():
            raise RuntimeError(
                f"Cannot get PID for container '{container_name(name)}' — is it running?"
            )
        pid = int(pid_result.stdout.strip())

        switch_phase(name, phase, config.network, pid)
        state.network_phase = phase
        save_state(state)

    def setup_vscode(self, name: str, config: VSCodeConfig) -> dict[str, str]:
        # Implemented in Phase 3
        from raven.backends.podman.vscode import setup_vscode_ssh
        return setup_vscode_ssh(name, config)

    def _wait_for_running(self, name: str, timeout: int = 30) -> None:
        """Poll until the container is running."""
        import time

        cname = container_name(name)
        svc = _service_name(name)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # Check if the systemd service itself has failed
            svc_result = run(
                ["systemctl", "--user", "is-failed", f"{svc}.service"],
                check=False,
            )
            if svc_result.stdout.strip() == "failed":
                raise RuntimeError(
                    f"Service '{svc}.service' failed to start.\n"
                    f"Run: systemctl --user status {svc}.service\n"
                    f"Run: journalctl --user -u {svc}.service"
                )

            result = run(
                ["podman", "inspect", "--format", "{{.State.Status}}", cname],
                check=False,
            )
            if result.returncode == 0:
                podman_status = result.stdout.strip().lower()
                if podman_status == "running":
                    return
                if podman_status in ("exited", "dead", "stopping"):
                    raise RuntimeError(
                        f"Container '{cname}' exited unexpectedly (status: {podman_status}).\n"
                        f"Run: systemctl --user status {svc}.service\n"
                        f"Run: journalctl --user -u {svc}.service"
                    )
            time.sleep(0.5)
        raise TimeoutError(
            f"Container '{cname}' did not reach running state within {timeout}s"
        )
