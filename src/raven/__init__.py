"""Raven — Isolated development environments with supply-chain attack protection."""

from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("raven")
except PackageNotFoundError:
    __version__ = "0.1.0"  # Fallback
