"""
Grain resolution module for the DataShark Engine.

Provides grain resolution logic to determine optimal aggregation levels
and prevent fan-out/double-counting errors.
"""

from __future__ import annotations

from datashark_mcp.planner.grain.grain_resolver import GrainResolver

__all__ = ["GrainResolver"]

