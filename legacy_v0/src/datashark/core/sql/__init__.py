"""
SQL Builder module for dialect-aware SQL generation.
"""

from datashark.core.sql.builder import SQLBuilder
from datashark.core.sql.dialects import (
    SQLDialect,
    PostgresDialect,
    DuckDBDialect,
    BigQueryDialect,
    RedshiftDialect,
)
from datashark.core.sql.join_resolver import JoinPathResolver

__all__ = [
    "SQLBuilder",
    "JoinPathResolver",
    "SQLDialect",
    "PostgresDialect",
    "DuckDBDialect",
    "BigQueryDialect",
    "RedshiftDialect",
]

