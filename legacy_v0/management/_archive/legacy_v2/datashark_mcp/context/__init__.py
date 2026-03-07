"""
datashark_mcp.context (compatibility package)

The canonical import path `datashark_mcp.context.*` is used widely across the codebase.
The actual implementations currently live under `datashark_mcp/_legacy/context/`.

This package makes `datashark_mcp.context` resolve to those legacy modules without
copying code or inventing new behavior.
"""

from __future__ import annotations

from pathlib import Path

# Extend this package's import path to include the legacy context directory so that
# `import datashark_mcp.context.api` loads `datashark_mcp/_legacy/context/api.py`, etc.
_legacy_context_dir = (Path(__file__).resolve().parent.parent / "_legacy" / "context").resolve()

# __path__ is defined by Python for packages; we append the legacy directory.
__path__.append(str(_legacy_context_dir))  # type: ignore[name-defined]



