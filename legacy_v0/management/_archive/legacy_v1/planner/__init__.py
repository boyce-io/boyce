"""
Planner module for the DataShark Engine.

Provides interfaces for transforming natural-language tasks into structured plans:
intent, concept map, join plan, SQL template, and final SQL output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class PlannerIntent:
    """
    High-level intent representation for a user task.

    Contract:
        - Captures the core question or objective in a structured form.
        - Contains no engine-specific execution details.
    """

    text: str


@dataclass
class PlannerPlan:
    """
    Structured planner output for a reasoning cycle.

    Contract:
        - Contains concept map, join plan, SQL template, and final SQL output placeholders.
        - Serves as the handoff artifact between planner, SQL builder, and executor.
    """

    intent: PlannerIntent
    concept_map: Dict[str, Any]
    join_plan: Dict[str, Any]
    sql_template: str
    sql: str


# Import Planner from planner.py for backward compatibility
from datashark_mcp.planner.planner import Planner

__all__ = ["Planner", "PlannerIntent", "PlannerPlan"]


