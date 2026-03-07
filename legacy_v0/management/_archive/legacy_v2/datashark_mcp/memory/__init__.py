"""
Memory module for the DataShark Engine.

Provides interfaces for lightweight adaptive behaviors scoped to correctness:
local pattern reinforcement, join-path biasing, and recent-query signals.
"""

from __future__ import annotations

from typing import Any, Dict


class MemorySubsystem:
    """
    Memory subsystem interface.

    Contract:
        - Tracks recent reasoning and execution signals relevant to correctness.
        - Provides read-only hints (e.g., join-path biases) to planner and engine.
        - Must remain lightweight and local; no long-term or user-identifying storage.
    """

    def __init__(self) -> None:
        """Initialize an empty memory subsystem (no business logic)."""
        pass

    def record_event(self, event: Dict[str, Any]) -> None:
        """
        Record a single reasoning or execution event.

        Contract:
            - Accepts structured events describing queries, joins, or outcomes.
            - May update internal state for future biasing.
            - Must not perform external I/O or persist state beyond the process.
        """
        raise NotImplementedError

    def get_biases(self) -> Dict[str, Any]:
        """
        Retrieve current bias signals for planning.

        Contract:
            - Returns aggregate hints such as preferred join paths or penalized patterns.
            - Must be deterministic given the same history.
        """
        raise NotImplementedError


