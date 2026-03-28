"""
Deterministic Query Kernel — process_request()

This module marks the boundary where the SQLBuilder will live.
It accepts a validated SemanticSnapshot and a StructuredFilter dict and
returns a SQL string.

Current status: Operational — SQLBuilder, JoinResolver, and dialect layer are fully wired.

Expected StructuredFilter shape (same as legacy api.py):
{
    "concept_map": {
        "entities":    ["entity:orders", ...],   # entity IDs to include
        "metrics":     ["field:orders:revenue"],  # measure field IDs
        "dimensions":  ["field:orders:status"],   # dimension field IDs
    },
    "filters": [
        {
            "field_id":  "field:orders:status",
            "operator":  "=",
            "value":     "active",
            "entity_id": "entity:orders"          # optional table qualification
        },
        ...
    ],
    "temporal_filters": [
        {
            "field_id": "field:orders:created_at",
            "operator": "trailing_interval",
            "value":    {"value": 12, "unit": "month"}
        },
        ...
    ],
    "join_path": ["entity:orders", "entity:customers"],  # explicit override (optional)
    "grain_context": {
        "aggregation_required": true
    },
    "policy_context": {
        "resolved_predicates": []   # row-level security predicates (future)
    },
    "dialect": "redshift",          # target SQL dialect
    # StructuredFilter v0.2 additions:
    "order_by": [                   # optional — ORDER BY clause
        {"field_id": "field:orders:created_at", "direction": "DESC"},
        {"metric_name": "total_revenue", "direction": "DESC"}
    ],
    "limit": 5,                     # optional — LIMIT clause
    "expressions": [                # optional — computed SELECT columns
        {
            "name": "full_name",
            "expression_type": "concatenation",
            "fields": [
                {"field_id": "field:customer:first_name", "field_name": "first_name"},
                {"field_id": "field:customer:last_name",  "field_name": "last_name"}
            ],
            "separator": " "
        }
    ]
}
"""

from __future__ import annotations

from typing import Any, Dict

from .sql.builder import SQLBuilder
from .types import SemanticSnapshot
from .validation import validate_snapshot


def process_request(
    snapshot: SemanticSnapshot,
    structured_filter: Dict[str, Any],
) -> str:
    """
    Generate SQL from a SemanticSnapshot and a StructuredFilter.

    Deterministic: same (snapshot, structured_filter) → same SQL byte-for-byte.
    No LLM touches this layer.

    Args:
        snapshot: Validated SemanticSnapshot containing the semantic model.
        structured_filter: Structured query intent produced by the Planner.
            See module docstring for the expected shape.

    Returns:
        A complete, executable SQL string targeting the snapshot's entities.

    Raises:
        ValueError: If snapshot is invalid or structured_filter is malformed.
    """
    errors = validate_snapshot(snapshot.model_dump(mode="json"))
    if errors:
        raise ValueError(f"Invalid snapshot passed to process_request: {errors}")

    dialect_name = structured_filter.get("dialect", "postgres")
    builder = SQLBuilder()
    builder.set_dialect(dialect_name)

    concept_map = structured_filter.get("concept_map", {})
    filters = concept_map.get("filters", []) or structured_filter.get("filters", [])
    planner_output = {
        "concept_map": {
            "entities":   concept_map.get("entities",   structured_filter.get("entities", [])),
            "fields":     concept_map.get("fields",     structured_filter.get("fields", [])),
            "metrics":    concept_map.get("metrics",    structured_filter.get("metrics", [])),
            "dimensions": concept_map.get("dimensions", structured_filter.get("dimensions", [])),
            "filters":    filters,
            # BUG-F: expressions rendered in SELECT clause via concept_map
            "expressions": structured_filter.get("expressions", []),
        },
        "filters":          filters,
        "temporal_filters": structured_filter.get("temporal_filters", []),
        "join_path":        structured_filter.get("join_path", []),
        "grain_context":    structured_filter.get("grain_context", {}),
        "policy_context":   structured_filter.get("policy_context", {"resolved_predicates": []}),
        # BUG-B: ORDER BY / LIMIT passthrough
        "order_by":         structured_filter.get("order_by", []),
        "limit":            structured_filter.get("limit"),
        # BUG-F: expressions passthrough (top-level for ORDER BY cross-reference)
        "expressions":      structured_filter.get("expressions", []),
    }
    return builder.build_final_sql(planner_output, snapshot)
