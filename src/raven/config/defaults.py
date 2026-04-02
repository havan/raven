"""Default values for raven configuration."""

from __future__ import annotations

# Registries allowed during the install phase by default.
# These are the minimum needed for npm, pip/uv, and Go module installs.
DEFAULT_REGISTRIES: list[str] = [
    # npm
    "registry.npmjs.org",
    "registry.yarnpkg.com",
    # PyPI
    "pypi.org",
    "files.pythonhosted.org",
    "bootstrap.pypa.io",
    # Go
    "proxy.golang.org",
    "sum.golang.org",
    "storage.googleapis.com",
    # GitHub (git clone, go get, pip install git+https)
    "github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
    "codeload.github.com",
    # Container registries (for image layers pulled during setup)
    "ghcr.io",
    "docker.io",
    "registry-1.docker.io",
    "auth.docker.io",
    "production.cloudflare.docker.com",
    # uv / astral
    "astral.sh",
]

# Known CDN CIDR ranges for major registries.
# DNS can return varying IPs for CDN-backed services; these CIDRs cover the
# entire CDN range so that nftables rules remain stable.
KNOWN_CDN_CIDRS: dict[str, list[str]] = {
    "registry.npmjs.org": ["104.16.0.0/12"],           # Cloudflare
    "registry.yarnpkg.com": ["104.16.0.0/12"],         # Cloudflare
    "pypi.org": ["151.101.0.0/16"],                    # Fastly
    "files.pythonhosted.org": ["151.101.0.0/16"],      # Fastly
    "objects.githubusercontent.com": ["185.199.108.0/22"],
    "raw.githubusercontent.com": ["185.199.108.0/22"],
}

# Default directories to purge during `raven reinstall --purge`
DEFAULT_PURGE_DIRS: list[str] = [
    "node_modules",
    ".venv",
    "venv",
    "vendor",
]
