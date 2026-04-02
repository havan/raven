# Raven

## Project Overview

**Raven** provides isolated development environments with built-in supply-chain attack protection. It aims to prevent malicious `postinstall` scripts from exfiltrating credentials, pivoting to the host, or silently modifying projects.

It works by placing each project into a rootless Podman container and enforcing a **two-phase network policy**:
1.  **Install Phase (`raven install`):** Network access is strictly limited to approved package registries (like npm, PyPI, GitHub, etc.) using `nftables` rules applied inside the container's network namespace.
2.  **Run Phase (`raven shell`, `raven code`):** A configurable policy applies (`open`, `restricted`, or `offline`), allowing for standard development with controlled exposure.

**Key Technologies & Dependencies:**
*   **Language:** Python (≥ 3.11)
*   **Container Engine:** Podman (≥ 4.4 with netavark backend)
*   **Networking:** `nftables` + `nsenter` (for per-container network isolation)
*   **Process Management:** `systemd` user services (Podman Quadlet) for persistent environments
*   **Core Libraries:** Typer (CLI), Pydantic (Configuration), Rich (Console Output)
*   **Tooling:** `uv` (Package manager)

## Architecture & Core Data Flow

1. User provides a `raven.yaml` config → validated by `config/schema.py` (Pydantic).
2. `backends/` owns the lifecycle: `create()` writes Quadlet unit files (`~/.config/containers/systemd/`) + `state.json`, `start()` calls `systemctl --user start`.
3. `network/` owns isolation: `phases.py` orchestrates DNS resolution → IP CIDR generation → `nsenter` execution of `nft` rules *inside* the container's network namespace.
4. State persists to `~/.local/share/raven/envs/<name>/state.json`.

### Module Responsibilities

*   **`config/`**
    *   `schema.py`: Pydantic models for the YAML schema (`EnvConfig`, `Source` union, `NetworkConfig`, `ReinstallConfig`).
    *   `loader.py`: `load_config(path)` / `save_config(config)`, supporting `${VAR}` interpolation.
    *   `defaults.py`: `DEFAULT_REGISTRIES` and `KNOWN_CDN_CIDRS` for stable nftables rules.
*   **`state/`**
    *   `store.py`: `load_state(name)` / `save_state(state)` backed by JSON. `list_env_names()` scans the envs directory.
*   **`backends/`**
    *   `base.py`: `Backend` ABC with standard lifecycle and network/VS Code setup methods.
    *   `podman/backend.py`: `PodmanBackend` using Quadlet. Containers named `raven-<envname>`, labeled `raven.managed=true`.
    *   `podman/systemd.py`: Generates `.container` and `.network` Quadlet files.
    *   `podman/vscode.py`: SSH keypair generation and injection, writes `~/.ssh/config` block, and launches VS Code.
*   **`network/`**
    *   `allowlists.py`: `resolve_allowlist(hostnames)` returning CIDRs (uses `KNOWN_CDN_CIDRS` fallback to `dnspython`).
    *   `nftables.py`: Generates `.nft` files and applies them using `sudo nsenter --net=/proc/<pid>/ns/net nft -f`.
    *   `phases.py`: Orchestrates phase switching (`install` vs `run`) and handles run-phase policies (`open`, `restricted`, `offline`).
*   **`util/`**
    *   `subprocess.py`: Execution utilities (`run()`, `stream_exec()`, `exec_replace()`, `run_as_root()`).
    *   `xdg.py`: Centralized XDG paths (`data_dir()`, `env_dir()`, `nft_rules_dir()`, `quadlet_dir()`).
*   **`cli/`**
    *   `app.py`: Main Typer entry point with global logging/debug options.
    *   `init_cmd.py`: Handles `raven init` (clone, template detection, policy prompt).
    *   `create.py`: Handles `raven create`.
    *   `env_commands.py`: Lifecycle management (`start`, `stop`, `shell`, `destroy`, `install`, `reinstall`, `run`).
    *   `network_cmd.py`: Live network control (`network status`, `network policy`, `allow`).
    *   `ps.py`: Process, port, and resource usage reporting.
    *   `export_cmd.py`: Config exporting (`--portable` support).
    *   `code.py`: VS Code Remote SSH integration.

## Building and Running

The project uses `uv` for dependency management and running development tasks.

### Setup
```bash
# Initialize the development environment and install dependencies
uv sync --dev
```

### Running the CLI
```bash
# Run the CLI directly from the source repository
uv run raven --help
uv run raven --debug <command>  # show DEBUG-level messages + subprocess calls
```

### Testing
```bash
# Run all tests (Integration tests require Podman and sudo access for nsenter)
uv run pytest tests/
```

## Development Conventions

*   **Type Safety:** Strict static typing with `mypy` (`strict = true`).
*   **Code Style:** `ruff` for linting and formatting (line-length 100).
*   **Testing:** Unit tests in `tests/unit/` (mocked), integration tests in `tests/integration/` (real Podman).

## Key Features & Implementations

### Network Isolation (Sudoers)
nftables rules are applied inside the container's network namespace via `nsenter`. A sudoers rule is mandatory:
```
<user> ALL=(root) NOPASSWD: /usr/bin/nsenter --net=/proc/*/ns/net /usr/sbin/nft -f /home/<user>/.local/share/raven/nft-rules/*.nft
<user> ALL=(root) NOPASSWD: /usr/bin/nsenter --net=/proc/*/ns/net /usr/sbin/nft delete table inet raven-*
```

### Live Network Control
Users can switch between `open`, `restricted`, and `offline` policies at runtime using `raven network policy`. `raven allow <host>` adds a host to the allowlist and immediately reapplies rules.

### Reinstall & Purge
`raven reinstall --purge` allows for cleaning up dependencies (e.g., `node_modules`, `.venv`) and re-running `setup_commands` under the restricted install-phase network without recreating the entire environment.

### VS Code Remote Dev
Uses standard **Remote - SSH**. Raven manages per-environment SSH keys and `~/.ssh/config` entries. The SSH port is assigned randomly at creation and persisted in `state.json`.
