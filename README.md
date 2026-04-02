# raven

Isolated development environments with supply-chain attack protection.

When you clone repos from GitHub and run `npm install` or `pip install`, every
package's `postinstall` script runs with your user's full network access. A
compromised package can exfiltrate credentials, pivot to your host, or silently
modify your project. Raven puts each project in a rootless Podman container and
enforces a **two-phase network policy**: during installation, only approved
package registries are reachable; during development, a configurable policy
applies. Your host stays untouched.

## How it works

```
raven create myproject --config raven.yaml    # create container from config
raven install myproject                       # npm ci / pip install with registry-only network
raven shell myproject                         # interactive shell (full dev network)
raven code myproject                          # open VS Code via Remote SSH
```

During `raven install`, nftables rules are applied on the **host side** of the
container's network interface. The container can only reach the domains you
explicitly allow (npm registry, PyPI, GitHub, etc.). Everything else is dropped.
When the install completes, rules are removed and the container gets normal
network access.

## Requirements

- Linux (kernel ≥ 5.11)
- [Podman](https://podman.io/) ≥ 4.4 with netavark backend
- Python ≥ 3.11
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- `nft` binary (`nftables` package)
- `systemd` user session with lingering enabled (for persistent environments)
- `openssh-server` installable inside your chosen container image (for
  `raven code`)

## Installation

```bash
git clone https://github.com/your-org/raven
cd raven
uv venv
uv pip install -e "." --python .venv/bin/python

# Make the raven command available globally
ln -s "$(pwd)/.venv/bin/raven" ~/.local/bin/raven
```

### Sudoers setup (required for network isolation)

Raven needs to apply nftables rules as root inside the container's network
namespace. Create `/etc/sudoers.d/raven`:

```
your-username ALL=(root) NOPASSWD: /usr/bin/nsenter --net=/proc/*/ns/net /usr/sbin/nft -f /home/your-username/.local/share/raven/nft-rules/*.nft
your-username ALL=(root) NOPASSWD: /usr/bin/nsenter --net=/proc/*/ns/net /usr/sbin/nft delete table inet raven-*
```

This limits sudo access to only the specific `nsenter`+`nft` commands raven
uses, scoped to its own rule files.

### Enable systemd linger (for persistent environments across logout)

```bash
loginctl enable-linger
```

Without this, environments stop when you log out. With it, they persist as
systemd user services.

## Quick start

1. Create a `raven.yaml` in your project directory:

```yaml
name: my-node-app
version: 1
backend: podman
image: mcr.microsoft.com/devcontainers/base:ubuntu

source:
  type: mount
  path: /path/to/your/project
  mount_path: /workspace

network:
  install_phase:
    allowed_registries:
      - registry.npmjs.org
      - github.com
  run_phase:
    policy: open
  port_forwards:
    - host: 3000
      container: 3000

setup_commands:
  - cd /workspace && npm ci

vscode:
  extensions:
    - dbaeumer.vscode-eslint
    - esbenp.prettier-vscode
```

2. Create and start the environment:

```bash
raven create my-node-app --config raven.yaml --start
```

3. Install dependencies with network isolation:

```bash
raven install my-node-app
```

4. Work in the environment:

```bash
raven shell my-node-app          # interactive shell
raven code my-node-app           # VS Code Remote SSH
raven run my-node-app npm test   # run a command
```

## Commands

| Command | Description |
|---|---|
| `raven create <name>` | Create environment from `raven.yaml` (or `--config path`) |
| `raven start <name>` | Start a stopped environment |
| `raven stop <name>` | Stop a running environment |
| `raven shell <name>` | Open an interactive shell |
| `raven install <name>` | Run `setup_commands` with restricted network |
| `raven reinstall <name>` | Re-run installs on demand (see below) |
| `raven run <name> <cmd...>` | Run a command inside the environment |
| `raven code <name>` | Open VS Code via Remote SSH |
| `raven list` | List all environments with status |
| `raven ps <name>` | Show processes, ports, and resource usage |
| `raven export <name>` | Print the config YAML (use `--portable` for sharing) |
| `raven destroy <name>` | Stop and remove the environment |

### Global options

```bash
raven --verbose <command>         # show INFO-level messages
raven --debug <command>           # show DEBUG-level messages + subprocess calls
raven --log-file path.log <cmd>   # write structured JSON Lines log to file
```

### raven reinstall

When `package.json` or `requirements.txt` changes during development, use
`reinstall` instead of recreating the environment:

```bash
raven reinstall my-node-app                    # re-run setup_commands
raven reinstall my-node-app --purge            # remove node_modules first, then reinstall
raven reinstall my-node-app --cmd "npm ci"     # run a specific command
raven reinstall my-node-app --purge --yes      # skip confirmation prompt
```

`--purge` removes directories listed in `reinstall.purge_dirs` (defaults:
`node_modules`, `.venv`, `venv`, `vendor`) relative to the workspace mount path.

## Config file reference

```yaml
name: my-project           # [a-z0-9][a-z0-9_-]* — must be unique
version: 1
backend: podman            # "podman" (default) | "firecracker" (coming soon)
image: mcr.microsoft.com/devcontainers/base:ubuntu  # any OCI image

source:
  type: mount              # "mount" — bind-mount a local directory
  path: /path/to/project   # absolute path on host
  mount_path: /workspace   # path inside container (default: /workspace)
  # OR:
  # type: clone            # "clone" — git clone at create time
  # url: https://github.com/owner/repo
  # ref: main

network:
  install_phase:
    allowed_registries:    # hostnames reachable during `raven install`
      - registry.npmjs.org
      - pypi.org
      - github.com
      # full default list covers npm, PyPI, Go, GitHub, and common registries
    allow_dns: true
  run_phase:
    policy: open           # "open" (default) | "allowlist" | "block"
    allowed_hosts: []      # used when policy=allowlist
  port_forwards:
    - host: 3000           # port on your host
      container: 3000      # port inside container
      protocol: tcp        # tcp (default) | udp
      bind_host: 127.0.0.1 # default; use 0.0.0.0 to expose to LAN

env_vars:
  NODE_ENV: development
  SECRET: "${SECRET}"      # ${VAR} is interpolated from host environment at runtime

resources:
  cpus: 4.0                # 0 = no limit
  memory: 4g               # "0" = no limit; accepts "512m", "4g", etc.

setup_commands:            # run sequentially during `raven install`
  - cd /workspace && npm ci
  - pip install -r requirements.txt

reinstall:
  purge_dirs:              # directories removed by `raven reinstall --purge`
    - node_modules
    - .venv
  commands:                # override setup_commands for reinstall (optional)
    - npm ci

vscode:
  extensions:              # installed when `raven code` connects
    - ms-python.python
    - esbenp.prettier-vscode
  settings:
    editor.formatOnSave: true
```

### Default allowed registries

If you don't specify `network.install_phase.allowed_registries`, raven allows:

- **npm**: `registry.npmjs.org`, `registry.yarnpkg.com`
- **PyPI**: `pypi.org`, `files.pythonhosted.org`, `bootstrap.pypa.io`
- **Go**: `proxy.golang.org`, `sum.golang.org`, `storage.googleapis.com`
- **GitHub**: `github.com`, `objects.githubusercontent.com`,
  `raw.githubusercontent.com`, `codeload.github.com`
- **Container registries**: `ghcr.io`, `docker.io` and its auth endpoints
- **uv**: `astral.sh`

## VS Code integration

`raven code <name>` connects VS Code using **Remote - SSH** (not Remote -
Containers). This is backend-agnostic and more reliable with Podman than the
devcontainer attach approach.

Raven generates a per-environment SSH keypair at
`~/.local/share/raven/envs/<name>/id_ed25519`, injects the public key into the
container, and writes an SSH config block to `~/.ssh/config`. Running
`raven code` then executes:

```
code --remote ssh-remote+raven-<name> /workspace
```

VS Code installs its server inside the container on first connect. Extensions
declared in `vscode.extensions` are available after the server is ready.

## Persistent environments

Environments are managed as **systemd user services** via [Podman Quadlet](https://docs.podman.io/en/latest/markdown/podman-systemd.unit.5.html).
When you run `raven create`, raven writes `.container` and `.network` unit files
to `~/.config/containers/systemd/` and reloads the user daemon. This means:

- `raven start` / `raven stop` map to `systemctl --user start/stop`
- Environments with `[Install] WantedBy=default.target` survive reboots
  automatically
- `loginctl enable-linger` makes them survive logout too

To reproduce an environment on another machine:

```bash
raven export my-project --portable > raven.yaml
# copy raven.yaml to the new machine, then:
raven create my-project --config raven.yaml
raven install my-project
```

## Network isolation: technical details

Raven creates one nftables table per environment (`table inet raven-<name>`)
with rules applied **inside the container's network namespace** via `nsenter`.
Rules use the OUTPUT chain so they intercept traffic at the point it leaves the
container, before it reaches the host. This works correctly with rootless Podman
+ netavark + pasta, where traffic bypasses the host's FORWARD chain entirely.

During the install phase:

- Allowed registries are resolved to IP CIDRs. For CDN-backed registries (npm
  via Cloudflare `104.16.0.0/12`, PyPI via Fastly `151.101.0.0/16`), known
  stable CIDR ranges are used instead of point-in-time DNS to avoid rules
  breaking when CDN IPs rotate.
- DNS (UDP/TCP port 53) is always allowed so hostnames resolve correctly.
- Loopback traffic (`oifname "lo"`) is always allowed.
- All other outbound traffic from the container is dropped.

When the install phase completes (or `policy: open` applies), raven deletes the
table entirely — no restrictions remain.

**Limitation:** DNS tunneling (data exfiltration encoded in DNS queries) is not
blocked by default. This is an advanced attack vector. If you need to defend
against it, add a DNS rate-limiting rule to your nftables configuration.

## Development

```bash
# First-time setup — creates .venv and installs all dependencies
uv sync --dev

# Run the CLI directly from the repo root
uv run raven --help

# Run tests
uv run pytest tests/             # all tests
uv run pytest tests/unit/        # unit tests only (no Podman needed)

# Lint and type-check
uv run ruff check src/
uv run mypy src/
```

See `examples/` for sample configs for Node.js and Python projects.

## Roadmap

- **Firecracker backend** — microVM isolation (separate kernel) for higher-trust
  projects
- `raven config init` — interactive wizard for first-time setup (sudoers,
  linger, shell completion)
- DNS-level logging and rate limiting for install phase
- Image digest pinning warnings
- `raven update` — pull a new image and recreate the container without
  destroying the workspace

## License

MIT
