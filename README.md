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
raven init myproject https://github.com/owner/repo  # clone + create + prompt for policy
raven install myproject                              # npm ci / pip install with registry-only network
raven shell myproject                                # interactive shell
raven code myproject                                 # open VS Code via Remote SSH
```

During `raven install`, nftables rules are applied inside the container's network
namespace via `nsenter`. The container can only reach the domains you explicitly
allow (npm registry, PyPI, GitHub, etc.). Everything else is dropped. When the
install completes, the run-phase policy takes over automatically.

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
your-username ALL=(root) NOPASSWD: /usr/local/bin/raven-nft-helper apply *
your-username ALL=(root) NOPASSWD: /usr/local/bin/raven-nft-helper delete *
```

This limits `sudo` access to only the specific helper that performs strict validation of the environment name, PID, and rule file path before applying any network rules.


### Enable systemd linger (for persistent environments across logout)

```bash
loginctl enable-linger
```

Without this, environments stop when you log out. With it, they persist as
systemd user services.

## Quick start

1. Initialize an environment from a Git repo:

```bash
raven init my-node-app https://github.com/owner/my-node-app
```

`raven init` clones the repo, detects the package manager from lockfiles, and
prompts you to choose a run-phase network policy:

```
Run phase network policy:
  1. open       — Full internet access
  2. restricted — Only allowed hosts (configure with raven allow)
  3. offline    — No outbound network access
Choose policy (number or name) [1]:
```

2. Install dependencies with network isolation:

```bash
raven install my-node-app
```

3. Work in the environment:

```bash
raven shell my-node-app          # interactive shell
raven code my-node-app           # VS Code Remote SSH
raven run my-node-app npm test   # run a command
```

4. If you need to reach a host that isn't in your allowlist:

```bash
raven allow my-node-app deb.debian.org   # add host and apply rules immediately
raven network status my-node-app         # inspect current policy and active CIDRs
```

## Commands

| Command | Description |
|---|---|
| `raven create <name>` | Create environment from `raven.yaml` (or `--config path`) |
| `raven init <name> <git-url>` | Clone a repo, detect template, prompt for policy, create environment |
| `raven start <name>` | Start a stopped environment (applies run-phase policy immediately) |
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
| `raven network status <name>` | Show current network policy, allowed hosts, and active CIDRs |
| `raven network policy <name> <policy>` | Switch run-phase policy live without restarting |
| `raven allow <name> <host>` | Add a host to the allowlist and apply rules immediately |

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

### raven network

Inspect and control the network policy of a running environment without restarting it.

```bash
raven network status myenv              # show phase, policy, allowed hosts, active CIDRs
raven network policy myenv open         # full internet access
raven network policy myenv restricted   # only hosts in allowed_hosts
raven network policy myenv offline      # no outbound traffic
```

### raven allow

Add a host to the run-phase allowlist and apply the updated rules immediately:

```bash
raven allow myenv apt.example.com
```

If the current policy is `open` or `offline`, this automatically switches to
`restricted` so the allowlist takes effect. The host is saved to `config.yaml`
and survives restarts.

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
    allowed_hosts:         # hostnames reachable during `raven install`
      - registry.npmjs.org
      - pypi.org
      - github.com
      # full default list covers npm, PyPI, Go, GitHub, and common registries
    allow_dns: true
  run_phase:
    policy: open           # "open" (default) | "restricted" | "offline"
    allowed_hosts: []      # used when policy=restricted
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

### Network policies

| Policy | Effect |
|---|---|
| `open` | Full internet access — nftables table is deleted entirely |
| `restricted` | Only `allowed_hosts` are reachable; all other outbound traffic is dropped |
| `offline` | No outbound traffic at all (loopback only) |

The run-phase policy is applied automatically when the container starts. You can
change it at any time without restarting:

```bash
raven network policy myenv offline     # lock it down
raven allow myenv deb.debian.org       # open one host → switches to restricted
raven network policy myenv open        # full access again
```

### Default allowed hosts (install phase)

If you don't specify `network.install_phase.allowed_hosts`, raven allows:

- **npm**: `registry.npmjs.org`, `registry.yarnpkg.com`
- **PyPI**: `pypi.org`, `files.pythonhosted.org`, `bootstrap.pypa.io`
- **Go**: `proxy.golang.org`, `sum.golang.org`, `storage.googleapis.com`
- **GitHub**: `github.com`, `objects.githubusercontent.com`,
  `raw.githubusercontent.com`, `codeload.github.com`
- **Container registries**: `ghcr.io`, `docker.io` and its auth endpoints
- **uv**: `astral.sh`

### Backward compatibility

Older config files that use `allowed_registries` (instead of `allowed_hosts`) or
the policy values `allowlist` / `block` (instead of `restricted` / `offline`)
are loaded transparently and upgraded to the new names on next save.

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

The run-phase policy is enforced immediately on `raven start` and whenever
`raven network policy` or `raven allow` is called. If `sudo nsenter` fails,
raven logs a warning and continues in degraded mode — no isolation, but the
container still runs.

During the install phase:

- Allowed hosts are resolved to IP CIDRs. For CDN-backed registries (npm via
  Cloudflare `104.16.0.0/12`, PyPI via Fastly `151.101.0.0/16`), known stable
  CIDR ranges are used instead of point-in-time DNS to avoid rules breaking when
  CDN IPs rotate.
- DNS (UDP/TCP port 53) is always allowed so hostnames resolve correctly.
- Loopback traffic (`oifname "lo"`) is always allowed.
- All other outbound traffic from the container is dropped.

When `policy: open` applies, raven deletes the table entirely — no restrictions
remain.

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
