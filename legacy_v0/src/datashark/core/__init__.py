"""
DataShark MCP Server

Provides AI-callable tools for database metadata exploration and query execution.
"""

__version__ = "0.1.0"

from datashark.core.types import (
    SemanticSnapshot,
    Entity,
    FieldDef,
    JoinDef,
    FieldType,
    JoinType,
    TemporalFilter,
    TemporalOperator,
    TemporalUnit,
    FilterDef,
    FilterOperator,
)

__all__ = [
    "SemanticSnapshot",
    "Entity",
    "FieldDef",
    "JoinDef",
    "FieldType",
    "JoinType",
    "TemporalFilter",
    "TemporalOperator",
    "TemporalUnit",
    "FilterDef",
    "FilterOperator",
]


