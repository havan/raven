"""Raven — Isolated development environments with supply-chain attack protection."""

try:
    from importlib.metadata import version as _version
except ImportError:
    # for python < 3.8
    from importlib_metadata import version as _version  # type: ignore[no-redef]

try:
    __version__ = _version("raven")
except Exception:
    __version__ = "0.1.0"  # Fallback
