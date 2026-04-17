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

Raven is a CLI tool that creates isolated dev environments (rootless Podman containers) to protect against supply chain attacks. The key idea: A flexible **Guard** system applies network isolation (via nftables) to the container. You can switch between presets like `open`, `registries` (for installs), `offline`, or `restricted` (custom allowlist) at any time, or run one-off commands under a specific guard.

### Core data flow

1. User provides a `raven.yaml` config → validated by `config/schema.py` (Pydantic). Supports `image` or `build` (local Dockerfile).
2. `backends/` owns the lifecycle: `create()` builds images (if needed) and writes a systemd `.service` unit file + `state.json`, `start()` regenerates the unit from config then calls `systemctl --user start`.
3. `network/` owns isolation: `guard.py` resolves presets (CWD -> `~/.local/share/raven/presets/` -> built-in) → DNS resolution → nftables rule generation → `sudo nsenter` application.
4. State persists to `~/.local/share/raven/envs/<name>/state.json`. Active guard is stored here.

### Module responsibilities

- **`config/schema.py`** — Pydantic models for the YAML schema. `EnvConfig` supports `image` or `build` (local image building). `NetworkConfig` uses a single `policy` (preset name) and `allowed_hosts`.
- **`config/loader.py`** — `load_config(path)` / `save_config(config)`. Supports `${VAR}` interpolation.
- **`config/defaults.py`** — `DEFAULT_REGISTRIES` and `KNOWN_CDN_CIDRS` for stable nftables rules.
- **`state/store.py`** — `load_state(name)` / `save_state(state)` backed by JSON. Tracks `guard_preset`.
- **`backends/base.py`** — `Backend` ABC. Methods: `create`, `start`, `stop`, `destroy`, `exec` (with `replace` opt), `shell`, `status`, `list_all`, `apply_guard`, `setup_vscode`.
- **`backends/podman/backend.py`** — `PodmanBackend`. Handles local image building (`podman build`) and systemd lifecycle.
- **`backends/podman/systemd.py`** — Generates plain systemd `.service` units.
- **`network/allowlists.py`** — `resolve_allowlist(hostnames)` returns CIDRs.
- **`network/nftables.py`** — Generates `.nft` rule files and applies via `raven-nft-helper`.
- **`network/guard.py`** — `resolve_preset(name)` and `apply_guard(env_name, preset, config, pid)`. Unifies all network isolation logic.
- **`util/subprocess.py`** — `run()`, `stream_exec()` (inherited terminal), `exec_replace()` (os.execvp).
- **`util/xdg.py`** — XDG paths: `data_dir()`, `env_dir(name)`, `nft_rules_dir()`, `presets_dir()`, `templates_dir()`.
- **`cli/app.py`** — Typer app. Commands: `ls` (summary), `show` (alias for `status` - detailed), `run` (supports `-g <guard>`), `guard`, `fw`, `setup`, `purge`.

### Backend pluggability

`FirecrackerBackend` in `backends/firecracker/backend.py` is a stub (all methods raise `NotImplementedError`). Adding a new backend: implement `Backend` ABC, register in `backends/__init__.py` `BACKENDS` dict, add the new `BackendType` enum value to `config/schema.py`.

### Network isolation requires sudo

nftables rules are applied inside the container's network namespace using a root-owned helper script (`raven-nft-helper`) to avoid insecure wildcards in `sudoers`.

A sudoers rule is needed:
```
<user> ALL=(root) NOPASSWD: /usr/local/bin/raven-nft-helper apply *
<user> ALL=(root) NOPASSWD: /usr/local/bin/raven-nft-helper delete *
```

> **Security note:** For security, `raven-nft-helper` should be root-owned and located in a protected directory like `/usr/local/bin/`. It validates the environment name, PID, and rule file path before invoking `nsenter` and `nft`.

Rules use the OUTPUT chain (not FORWARD) because rootless Podman with netavark+pasta bypasses the host FORWARD chain entirely. If `sudo nsenter` fails, `apply_guard()` logs a warning and continues (degraded mode — no isolation, but the process still runs).

### VS Code remote dev

`raven code <name>` uses SSH mode (not devcontainer attach). This makes it backend-agnostic — the same code path will work when Firecracker is implemented. The SSH port is assigned at `raven create` time (random free port stored in `state.json`).
