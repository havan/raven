# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# First-time setup (creates .venv and installs all deps)
uv sync --dev

# Run the CLI from the repo root
uv run raven --help
uv run raven --debug <command>

# Run tests
uv run pytest tests/
uv run pytest tests/unit/                          # unit only (no Podman needed)
uv run pytest tests/unit/test_config.py            # single file
uv run pytest tests/unit/test_config.py::test_name # single test

# Lint and type-check
uv run ruff check src/
uv run mypy src/
```

`uv sync --dev` is the only setup step — uv creates the venv automatically. After that, every `uv run` command re-syncs if `pyproject.toml` changed.

## Architecture

Raven is a CLI tool that creates isolated dev environments (rootless Podman containers) to protect against supply chain attacks. The key idea: `raven install` applies nftables allowlist rules so only approved package registries are reachable while `npm install`/`pip install` runs. After install, the environment reverts to normal network policy.

### Core data flow

1. User provides a `raven.yaml` config → validated by `config/schema.py` (Pydantic)
2. `backends/` owns the lifecycle: `create()` writes Quadlet unit files + `state.json`, `start()` calls `systemctl --user start`
3. `network/` owns isolation: `phases.py` orchestrates DNS resolution → nftables rule generation → `sudo nft -f` application
4. State persists to `~/.local/share/raven/envs/<name>/state.json`

### Module responsibilities

- **`config/schema.py`** — Pydantic models for the YAML schema. `EnvConfig` is the top-level model; `Source` is a discriminated union on `source.type` (`mount` vs `clone`).
- **`config/loader.py`** — `load_config(path)` / `save_config(config)`. Supports `${VAR}` interpolation in `env_vars`.
- **`config/defaults.py`** — `DEFAULT_REGISTRIES` and `KNOWN_CDN_CIDRS` (CDN CIDR ranges for npm/PyPI/GitHub that are used instead of DNS for stable nftables rules).
- **`state/store.py`** — `load_state(name)` / `save_state(state)` backed by JSON at the XDG data path. `list_env_names()` scans the envs directory.
- **`backends/base.py`** — `Backend` ABC. All backends implement: `create`, `start`, `stop`, `destroy`, `exec`, `shell`, `status`, `list_all`, `get_info`, `apply_network_phase`, `setup_vscode`.
- **`backends/__init__.py`** — `get_backend(config)` factory; maps `BackendType` enum to implementation class.
- **`backends/podman/backend.py`** — `PodmanBackend`. Uses Quadlet files for systemd integration (not the deprecated `podman generate systemd`). Container name convention: `raven-<envname>`, all containers labelled `raven.managed=true`.
- **`backends/podman/systemd.py`** — Generates `.container` and `.network` Quadlet files into `~/.config/containers/systemd/`.
- **`backends/podman/vscode.py`** — SSH keypair generation, injects pubkey into container, writes `~/.ssh/config` block with markers `# raven-begin/<name>` / `# raven-end/<name>`, launches `code --remote ssh-remote+raven-<name>`.
- **`network/allowlists.py`** — `resolve_allowlist(hostnames)` returns CIDRs; uses `KNOWN_CDN_CIDRS` first, falls back to `dnspython`.
- **`network/nftables.py`** — Generates `.nft` rule files to `~/.local/share/raven/nft-rules/`. Applies them with `sudo nft -f <file>`. One nftables table per env (`table inet raven-<name>`), matching on the Podman bridge interface name.
- **`network/phases.py`** — `switch_phase(env_name, phase, network_config)`. Install phase: resolve IPs → write rule file → apply. Run/open phase: `nft delete table`.
- **`util/subprocess.py`** — `run()` for captured output, `stream_exec()` for inherited terminal, `exec_replace()` for shell/interactive commands (`os.execvp`).
- **`util/xdg.py`** — All XDG paths in one place: `data_dir()`, `env_dir(name)`, `nft_rules_dir()`, `quadlet_dir()`.
- **`cli/app.py`** — Typer app with global `--verbose`/`--debug`/`--log-file` options that call `setup_logging()` before any command runs.

### Backend pluggability

`FirecrackerBackend` in `backends/firecracker/backend.py` is a stub (all methods raise `NotImplementedError`). Adding a new backend: implement `Backend` ABC, register in `backends/__init__.py` `BACKENDS` dict, add the new `BackendType` enum value to `config/schema.py`.

### Network isolation requires sudo

nftables rules run as root. A sudoers rule is needed:
```
<user> ALL=(root) NOPASSWD: /usr/sbin/nft -f /home/<user>/.local/share/raven/nft-rules/*.nft
<user> ALL=(root) NOPASSWD: /usr/sbin/nft delete table inet raven-*
```
If `sudo nft` fails, `apply_network_phase()` logs a warning and continues (degraded mode — no isolation, but the install still runs).

### VS Code remote dev

`raven code <name>` uses SSH mode (not devcontainer attach). This makes it backend-agnostic — the same code path will work when Firecracker is implemented. The SSH port is assigned at `raven create` time (random free port stored in `state.json`).
