# Raven

## Project Overview

**Raven** provides isolated development environments with built-in supply-chain attack protection. It aims to prevent malicious `postinstall` scripts from exfiltrating credentials, pivoting to the host, or silently modifying projects.

It works by placing each project into a rootless Podman container and enforcing a **two-phase network policy**:
1.  **Install Phase (`raven install`):** Network access is strictly limited to approved package registries (like npm, PyPI, GitHub, etc.) using host-side `nftables` rules.
2.  **Run Phase (`raven shell`, `raven code`):** A configurable policy applies (default is open), and the container gains broader network access for standard development.

**Key Technologies & Dependencies:**
*   **Language:** Python (≥ 3.11)
*   **Container Engine:** Podman (≥ 4.4 with netavark backend)
*   **Networking:** `nftables` (for host-side network isolation rules)
*   **Process Management:** `systemd` user services (Podman Quadlet) for persistent environments
*   **Core Libraries:** Typer (CLI), Pydantic (Configuration), Rich (Console Output)
*   **Tooling:** `uv` (Package manager)

## Architecture & Core Data Flow

1. User provides a `raven.yaml` config → validated by `config/schema.py` (Pydantic).
2. `backends/` owns the lifecycle: `create()` writes Quadlet unit files + `state.json`, `start()` calls `systemctl --user start`.
3. `network/` owns isolation: `phases.py` orchestrates DNS resolution → nftables rule generation → `sudo nft -f` application.
4. State persists to `~/.local/share/raven/envs/<name>/state.json`.

### Module Responsibilities

*   **`config/`**
    *   `schema.py`: Pydantic models for the YAML schema (`EnvConfig`, `Source` union for mount vs clone).
    *   `loader.py`: `load_config(path)` / `save_config(config)`, supporting `${VAR}` interpolation.
    *   `defaults.py`: `DEFAULT_REGISTRIES` and `KNOWN_CDN_CIDRS` for stable nftables rules.
*   **`state/`**
    *   `store.py`: `load_state(name)` / `save_state(state)` backed by JSON. `list_env_names()` scans the envs directory.
*   **`backends/`**
    *   `base.py`: `Backend` ABC with standard lifecycle and network/VS Code setup methods.
    *   `__init__.py`: `get_backend(config)` factory mapping `BackendType` to implementation.
    *   `podman/backend.py`: `PodmanBackend` using Quadlet. Containers named `raven-<envname>`, labeled `raven.managed=true`.
    *   `podman/systemd.py`: Generates `.container` and `.network` Quadlet files.
    *   `podman/vscode.py`: SSH keypair generation and injection, writes `~/.ssh/config` block, and launches VS Code.
*   **`network/`**
    *   `allowlists.py`: `resolve_allowlist(hostnames)` returning CIDRs (uses `KNOWN_CDN_CIDRS` fallback to `dnspython`).
    *   `nftables.py`: Generates and applies `.nft` files (`sudo nft -f`). One table per env matching the Podman bridge.
    *   `phases.py`: Orchestrates phase switching (resolving IPs, applying rules, or deleting the table).
*   **`util/`**
    *   `subprocess.py`: Execution utilities (`run()`, `stream_exec()`, `exec_replace()`).
    *   `xdg.py`: Centralized XDG paths (`data_dir()`, `env_dir()`, `nft_rules_dir()`, `quadlet_dir()`).
*   **`cli/`**
    *   `app.py`: Typer app with global logging/debug options.

## Building and Running

The project uses `uv` for dependency management and running development tasks, and `hatchling` as the build backend.

### Setup
```bash
# Initialize the development environment and install dependencies
uv sync --dev
```
*Note: `uv sync --dev` is the only setup step — `uv` creates the venv automatically. After that, every `uv run` command re-syncs if `pyproject.toml` changed.*

### Running the CLI
```bash
# Run the CLI directly from the source repository
uv run raven --help
uv run raven --debug <command>  # show DEBUG-level messages + subprocess calls
```

### Testing
```bash
# Run all tests (Integration tests may require a working Podman setup)
uv run pytest tests/

# Run unit tests only
uv run pytest tests/unit/

# Run a single test file
uv run pytest tests/unit/test_config.py

# Run a single specific test
uv run pytest tests/unit/test_config.py::test_name
```

### Linting & Formatting
```bash
# Run Ruff for linting
uv run ruff check src/

# Run mypy for static type checking
uv run mypy src/
```

## Development Conventions

*   **Type Safety:** The project enforces strict static typing. `mypy` is configured with `strict = true` in `pyproject.toml`. All new code should include comprehensive type hints.
*   **Code Style:** `ruff` is used for linting and formatting. It targets Python 3.11 with a configured line-length limit of 100 characters.
*   **Testing Practices:** Tests are organized into `tests/unit/` and `tests/integration/` directories. Unit tests should be designed to run without needing Podman or host system modifications.

## Key Features & Implementations

### Backend Pluggability
Adding a new backend (e.g., the planned `FirecrackerBackend`) requires implementing the `Backend` ABC, registering it in the `backends/__init__.py` `BACKENDS` dict, and adding a new `BackendType` enum value in `config/schema.py`.

### Network Isolation (Sudoers)
nftables rules must run as root. A sudoers rule is needed to avoid password prompts during isolation phases:
```
<user> ALL=(root) NOPASSWD: /usr/sbin/nft -f /home/<user>/.local/share/raven/nft-rules/*.nft
<user> ALL=(root) NOPASSWD: /usr/sbin/nft delete table inet raven-*
```
If `sudo nft` fails, `apply_network_phase()` will log a warning and continue in a degraded mode (no isolation, but the install still runs).

### VS Code Remote Dev
`raven code <name>` uses SSH mode, not the "devcontainer attach" approach. This ensures backend-agnostic compatibility. The SSH port is assigned randomly at `raven create` time and stored in `state.json`.