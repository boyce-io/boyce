"""
Safety Kernel utilities for deterministic, Redshift-safe SQL execution.

This package implements:
- Redshift 1.0 guardrails and SQL transformations
- Strict Pydantic handshake models for SemanticSnapshot-like payloads
"""

from .redshift_guardrails import (
    transform_sql_for_redshift_safety,
    lint_redshift_compat,
)
from .models import (
    RelationshipType,
    MeasureAggType,
    HandshakeEntity,
    HandshakeDimension,
    HandshakeMeasure,
    HandshakeJoin,
    HandshakeSemanticSnapshot,
)

__all__ = [
    # Guardrails
    "transform_sql_for_redshift_safety",
    "lint_redshift_compat",
    # Handshake models
    "RelationshipType",
    "MeasureAggType",
    "HandshakeEntity",
    "HandshakeDimension",
    "HandshakeMeasure",
    "HandshakeJoin",
    "HandshakeSemanticSnapshot",
]


