"""
Executor module for the DataShark Engine.

Provides interfaces for executing SQL, handling errors, and coordinating the
error recovery contract between planner and executor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ExecutionResult:
    """
    Structured result for a single execution attempt.

    Contract:
        - Contains result metadata (status, error info, row counts, etc.).
        - Does not dictate how results are rendered in any particular UI.
    """

    success: bool
    payload: Any
    error: Dict[str, Any]


class ExecutionLoop:
    """
    Execution loop interface.

    Contract:
        - Accepts deterministic SQL produced by the SQL builder.
        - Executes SQL against a configured warehouse or simulation layer.
        - Surfaces failures via a structured error surface suitable for planner recovery.
        - Must honor the Error Recovery Contract defined in the architecture.
    """

    def __init__(self) -> None:
        """Initialize the execution loop (no business logic)."""
        pass

    def execute_sql(self, sql: str) -> ExecutionResult:
        """
        Execute a single SQL statement.

        Contract:
            - Accepts a fully-formed, deterministic SQL string.
            - Returns an ExecutionResult describing success/failure and payload.
            - Must not perform retries or recovery; that belongs to the higher-level loop.
        """
        raise NotImplementedError

    def run_with_recovery(self, sql: str) -> ExecutionResult:
        """
        Execute SQL with an error-aware loop.

        Contract:
            - Coordinates execution attempts and error reporting.
            - Surfaces structured error context for use by the planner recovery pipeline.
            - Must not perform semantic rewrites itself; it only executes and reports.
        """
        raise NotImplementedError


