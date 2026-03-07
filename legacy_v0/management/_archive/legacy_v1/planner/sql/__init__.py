"""
SQL generation module for the DataShark Engine.

Provides deterministic SQL building from planner output,
ensuring consistent formatting and policy injection.
"""

from __future__ import annotations

from datashark_mcp.planner.sql.sql_builder import SQLBuilder

__all__ = ["SQLBuilder"]

