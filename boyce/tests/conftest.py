"""
Pytest configuration for the boyce test suite.

Imports the real 'mcp' package at session start so that capability tests
(test_null_trap_detection.py, verify_eyes.py, etc.) cannot replace it with
a MagicMock stub. Those files guard their stub with:

    if "mcp" not in sys.modules:
        _mcp_stub = MagicMock()
        sys.modules["mcp"] = _mcp_stub
        ...

conftest.py is loaded by pytest before any test module's module-level code,
so importing mcp here guarantees the real package wins.
"""

import mcp  # noqa: F401  — must be imported before test modules install a stub
