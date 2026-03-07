"""
Minimal Kernel Entrypoint

This module provides the minimal entrypoint for the DataShark Kernel:
process_request(snapshot, structured_filter) -> SQL

This is the "Zero-Agency Determinism" layer - it takes a valid SemanticSnapshot
and a StructuredFilter and compiles byte-stable SQL. No LLM touches this layer.
"""

from __future__ import annotations

from typing import Any, Dict

from datashark.core.sql.builder import SQLBuilder
from datashark.core.types import SemanticSnapshot
from datashark.core.validation import validate_snapshot


def process_request(snapshot: SemanticSnapshot, structured_filter: Dict[str, Any]) -> str:
    """
    Process a request through the Kernel.
    
    This is the minimal entrypoint that takes a valid SemanticSnapshot and
    a structured filter request and produces deterministic SQL.
    
    **Contract:** The snapshot MUST pass validation before SQL generation.
    This function validates the snapshot and raises ValueError if invalid.
    
    Args:
        snapshot: Valid SemanticSnapshot (must pass validation)
        structured_filter: Structured filter dictionary containing:
            - concept_map: Dictionary with entities, fields, metrics, dimensions
            - filters: List of FilterDef objects
            - temporal_filters: List of TemporalFilter objects
            - join_path: List of join paths (optional, can be inferred from snapshot)
            - grain_context: Dictionary with grain information
            - policy_context: Dictionary with policy predicates (optional)
            - dialect: Optional dialect name (defaults to "postgres")
    
    Returns:
        SQL string (deterministic, byte-stable)
    
    Raises:
        ValueError: If snapshot is invalid or structured_filter is malformed
    """
    # Step 1: Validate snapshot (MUST validate before SQL generation)
    snapshot_dict = snapshot.model_dump(mode='json')
    validation_errors = validate_snapshot(snapshot_dict)
    if validation_errors:
        error_msg = "Snapshot validation failed:\n" + "\n".join(f"  - {err}" for err in validation_errors)
        raise ValueError(error_msg)
    
    # Step 2: Extract dialect from structured_filter or default to postgres
    dialect_name = structured_filter.get("dialect", "postgres")
    
    # Initialize SQLBuilder with the specified dialect
    builder = SQLBuilder()
    builder.set_dialect(dialect_name)
    
    # Build SQL from structured filter
    # The SQLBuilder expects a planner_output-like structure
    # Extract concept_map (Planner puts everything in concept_map)
    concept_map = structured_filter.get("concept_map", {})
    
    # Extract filters from concept_map (Planner format) or top-level (legacy format)
    filters = concept_map.get("filters", []) or structured_filter.get("filters", [])
    
    planner_output = {
        "concept_map": {
            "entities": concept_map.get("entities", structured_filter.get("entities", [])),
            "fields": concept_map.get("fields", structured_filter.get("fields", [])),
            "metrics": concept_map.get("metrics", structured_filter.get("metrics", [])),
            "dimensions": concept_map.get("dimensions", structured_filter.get("dimensions", [])),
            "filters": filters  # Filters are in concept_map for SQLBuilder
        },
        "filters": filters,  # Also at top level for compatibility
        "temporal_filters": structured_filter.get("temporal_filters", []),
        "join_path": structured_filter.get("join_path", []),
        "grain_context": structured_filter.get("grain_context", {}),
        "policy_context": structured_filter.get("policy_context", {
            "resolved_predicates": []
        }),
    }
    
    # Build final SQL using the snapshot
    sql = builder.build_final_sql(planner_output, snapshot)
    
    return sql
