"""DataShark — Privacy-First Data Compiler and DBeaver Plugin Backend."""

from datashark.core.types import (
    Entity,
    EntityType,
    FieldDef,
    FieldType,
    SemanticSnapshot,
)
from datashark.core.sql.builder import SQLBuilder
from datashark.core.sql.dialects import (
    BigQueryDialect,
    PostgresDialect,
    RedshiftDialect,
)
from datashark.core.graph import SemanticGraph

# Alias for Agent API: Field = FieldDef
Field = FieldDef

__version__ = "1.0.0"

__all__ = [
    "BigQueryDialect",
    "Entity",
    "EntityType",
    "Field",
    "FieldDef",
    "FieldType",
    "PostgresDialect",
    "RedshiftDialect",
    "SemanticGraph",
    "SemanticSnapshot",
    "SQLBuilder",
]
