# raven

Isolated development environments with supply-chain attack protection.

When you clone repos from GitHub and run `npm install` or `pip install`, every
package's `postinstall` script runs with your user's full network access. A
compromised package can exfiltrate credentials, pivot to your host, or silently
modify your project. Raven puts each project in a rootless Podman container and
enforces a **flexible network guard**: you can switch between policies like
`registries` (only approved registries), `restricted` (custom allowlist),
`offline`, or `open` at any time. Your host stays untouched.

## How it works

```bash
raven init myproject https://github.com/owner/repo  # clone + create + prompt for guard
raven setup myproject                                # run setup_commands under registries guard
raven shell myproject                                # interactive shell
raven code myproject                                 # open VS Code via Remote SSH
```

Raven uses `nftables` rules applied inside the container's network namespace via
`nsenter`. The container can only reach the domains you explicitly allow (npm
registry, PyPI, GitHub, etc.) when a restrictive guard is active. Everything else
is dropped. You can switch guards on the fly or run one-off commands under a
specific guard.

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
prompts you to choose an initial network guard:

```text
Choose initial network guard:
  1. open       — Full internet access
  2. restricted — Only allowed hosts (configure with raven allow)
  3. offline    — No outbound network access
Choose policy [open]:
```

2. Run setup commands with network isolation:

```bash
raven setup my-node-app
```
This runs the `setup_commands` defined in the template (e.g., `npm install`) under the `registries` guard.

3. Work in the environment:

```bash
raven shell my-node-app                  # interactive shell
raven code my-node-app                   # VS Code Remote SSH
raven run my-node-app -- npm test        # run a command
raven run my-node-app -g offline -- env  # run a command while offline
```

4. If you need to reach a host that isn't in your allowlist:

```bash
raven allow my-node-app deb.debian.org   # add host and switch to restricted guard
raven show my-node-app                   # inspect current guard and status
```

## Commands

| Command | Description |
|---|---|
| `raven create <name>` | Create environment from `raven.yaml` (or `--config path`) |
| `raven init <name> <git-url>` | Clone a repo, detect template, prompt for guard, create environment |
| `raven setup <name>` | Run `setup_commands` under a guard (default: `registries`) |
| `raven start <name>` | Start a stopped environment |
| `raven stop <name>` | Stop a running environment |
| `raven restart <name>` | Restart an environment (stop then start) |
| `raven shell <name>` | Open an interactive shell |
| `raven run <name> <cmd...>` | Run a command (optional: `-g <guard>`) |
| `raven purge <name>` | Remove dependency directories (node_modules, etc.) |
| `raven guard <name> <preset>`| Switch network guard live (open, registries, offline, restricted) |
| `raven allow <name> <host>` | Add a host to allowlist and switch to restricted guard |
| `raven fw <name> <mapping>` | Add port forwarding (e.g., `8080:80`) |
| `raven show <name>` | Detailed status for one environment |
| `raven ls` | List all environments (alias: `list`) |
| `raven logs [name]` | Stream or show logs for an environment |
| `raven code <name>` | Open VS Code via Remote SSH |
| `raven top <name>` | Show processes and resource usage |
| `raven ps [name]` | List environments or show processes for one |
| `raven export <name>` | Print the config YAML (use `--portable` for sharing) |
| `raven config` | View or edit configuration interactively |
| `raven destroy <name>` | Stop and remove the environment |

### Global options

```bash
raven --verbose <command>         # show INFO-level messages
raven --debug <command>           # show DEBUG-level messages + subprocess calls
raven --log-file path.log <cmd>   # write structured JSON Lines log to file
```

### Network Guards

Raven uses "presets" to control network access. You can switch them live using `raven guard` or use them for one-off commands with `raven run -g`.

| Guard | Effect |
|---|---|
| `open` | Full internet access — no restrictions |
| `registries` | Access to common package registries (npm, PyPI, Go, etc.) |
| `restricted` | Only `allowed_hosts` defined in your config are reachable |
| `offline` | No outbound traffic at all |

You can also create **custom presets** by placing a `<name>.yaml` file in:
1. The current working directory.
2. `~/.local/share/raven/presets/`.

Example `mypreset.yaml`:
```yaml
allowed_hosts:
  - myapi.example.com
  - internal-git.corp
```

### Port Forwarding

Add port mappings on the fly:

```bash
raven fw my-env 8080:80
raven restart my-env
```
*(Note: Podman requires a container restart to apply new port mappings).*

## Config file reference

```yaml
name: my-project           # [a-z0-9][a-z0-9_-]* — must be unique
version: 1
backend: podman            # "podman" (default) | "firecracker"

# Use an existing image:
image: mcr.microsoft.com/devcontainers/base:ubuntu
# OR build from a local Dockerfile:
# build:
#   dockerfile: Dockerfile
#   context: .

source:
  type: mount              # "mount" — bind-mount a local directory
  path: /path/to/project   # absolute path on host
  mount_path: /workspace   # path inside container (default: /workspace)

network:
  policy: open             # active guard (open, registries, restricted, offline)
  allowed_hosts:           # used when policy=restricted
    - myapi.example.com
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

setup_commands:            # run sequentially during `raven setup`
  - cd /workspace && npm ci

purge:
  purge_dirs:              # directories removed by `raven purge`
    - node_modules
    - .venv

vscode:
  extensions:              # installed when `raven code` connects
    - ms-python.python
  settings:
    editor.formatOnSave: true
```

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

## Persistent environments

Environments are managed as **systemd user services**.
When you run `raven create`, raven writes a service unit file to `~/.config/systemd/user/`.

- `raven start` / `raven stop` map to `systemctl --user start/stop`
- Environments survive reboots automatically
- `loginctl enable-linger` makes them survive logout too

## Network isolation: technical details

Raven creates one nftables table per environment (`table inet raven-<name>`)
with rules applied **inside the container's network namespace** via `nsenter`.
Rules use the OUTPUT chain so they intercept traffic at the point it leaves the
container.

When `policy: open` applies, raven deletes the table entirely — no restrictions
remain.

### Default allowed hosts (`registries` guard)

- **npm**: `registry.npmjs.org`, `registry.yarnpkg.com`
- **PyPI**: `pypi.org`, `files.pythonhosted.org`, `bootstrap.pypa.io`
- **Go**: `proxy.golang.org`, `sum.golang.org`, `storage.googleapis.com`
- **GitHub**: `github.com`, `objects.githubusercontent.com`,
  `raw.githubusercontent.com`, `codeload.github.com`
- **Container registries**: `ghcr.io`, `docker.io`
- **uv**: `astral.sh`

## Development

```bash
# First-time setup — creates .venv and installs all dependencies
uv sync --dev

# Run the CLI directly from the repo root
uv run raven --help

# Run tests
uv run pytest tests/
```

## License

MIT
